#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# ///
"""
migrate_to_sqlite.py — One-time migration from markdown-based job-application
pipeline to a SQLite database.

Step 1 of the SQLite migration plan. Additive only — no source files are deleted.

Usage:
    uv run scripts/migrate_to_sqlite.py                        # real memory dir
    uv run scripts/migrate_to_sqlite.py --memory-dir /tmp/test # override
    uv run scripts/migrate_to_sqlite.py --force                # overwrite existing DB
    uv run scripts/migrate_to_sqlite.py --dry-run              # parse, print, no writes
"""
import argparse
import os
import pathlib
import re
import sqlite3
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def default_memory_dir() -> pathlib.Path:
    """Resolve the memory dir from $PLYTOOLS_MEMORY_DIR — no hardcoded default.
    Callers without the env var set must pass --memory-dir explicitly."""
    env = os.environ.get("PLYTOOLS_MEMORY_DIR")
    if not env:
        sys.exit(
            "PLYTOOLS_MEMORY_DIR is not set and no --memory-dir was provided.\n"
            "Set the env var to the directory containing applications/, "
            "or pass --memory-dir <path>."
        )
    return pathlib.Path(env).expanduser()


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS applications (
  id            INTEGER PRIMARY KEY,
  company_slug  TEXT NOT NULL,
  role_slug     TEXT NOT NULL,
  company       TEXT NOT NULL,
  role          TEXT NOT NULL,
  stage         TEXT NOT NULL DEFAULT 'Discovered',
  priority      INTEGER,
  last_action   TEXT,
  next_step     TEXT,
  notes         TEXT,
  updated       TEXT NOT NULL,
  created_at    TEXT NOT NULL,
  UNIQUE (company_slug, role_slug)
);
CREATE INDEX IF NOT EXISTS idx_applications_stage ON applications(stage);
CREATE INDEX IF NOT EXISTS idx_applications_priority ON applications(priority);

CREATE TABLE IF NOT EXISTS jd (
  application_id   INTEGER PRIMARY KEY REFERENCES applications(id) ON DELETE CASCADE,
  url              TEXT,
  location         TEXT,
  employment       TEXT,
  compensation_raw TEXT,
  comp_low         INTEGER,
  comp_high        INTEGER,
  fetched_at       TEXT,
  body_path        TEXT
);

CREATE TABLE IF NOT EXISTS contacts (
  id             INTEGER PRIMARY KEY,
  application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  name           TEXT NOT NULL,
  role           TEXT,
  linkedin       TEXT,
  email          TEXT,
  tier           TEXT,
  notes          TEXT
);
CREATE INDEX IF NOT EXISTS idx_contacts_app ON contacts(application_id);

CREATE TABLE IF NOT EXISTS drafts (
  id             INTEGER PRIMARY KEY,
  application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  path           TEXT NOT NULL UNIQUE,
  name           TEXT NOT NULL,
  persona        TEXT,
  variant        TEXT,
  target         TEXT,
  updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_drafts_app ON drafts(application_id);
"""


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Convert a display name to a filesystem-style slug (lowercase, hyphens)."""
    s = text.lower().strip()
    # Replace non-alphanumeric chars (except existing hyphens) with hyphens
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s


# ---------------------------------------------------------------------------
# index.md parser
# ---------------------------------------------------------------------------

def parse_index(text: str) -> list[dict]:
    """
    Parse the pipe-table in index.md.

    Expected columns: Company | Role | Stage | Last action | Next | Updated
    Returns a list of dicts with keys: company, role, stage, last_action,
    next_step, updated, company_slug, role_slug.
    """
    rows = []
    for line in text.splitlines():
        line = line.strip()
        # Skip blank lines, separator lines, and the header row
        if not line.startswith("|"):
            continue
        if re.match(r"^\|[-| ]+\|$", line):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 6:
            continue
        company, role, stage, last_action, next_step, updated = (
            parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
        )
        # Skip the header row (contains "Company" literally)
        if company.lower() == "company":
            continue
        rows.append({
            "company": company,
            "role": role,
            "stage": stage,
            "last_action": last_action or None,
            "next_step": next_step or None,
            "updated": updated or datetime.now(timezone.utc).date().isoformat(),
            "company_slug": slugify(company),
            "role_slug": slugify(role),
        })
    return rows


# ---------------------------------------------------------------------------
# status.md parser
# ---------------------------------------------------------------------------

# Bullet fields we extract as structured columns
_STATUS_FIELDS = {
    "stage": re.compile(r"^\s*-\s+\*\*Stage:\*\*\s*(.+)$", re.IGNORECASE),
    "priority": re.compile(r"^\s*-\s+\*\*Priority:\*\*\s*(.+)$", re.IGNORECASE),
    "last_action": re.compile(r"^\s*-\s+\*\*Last action:\*\*\s*(.+)$", re.IGNORECASE),
    "next_step": re.compile(r"^\s*-\s+\*\*Next step:\*\*\s*(.+)$", re.IGNORECASE),
}

# Fields that appear in status.md but belong to jd.md in some files — skip entirely
# (do not include in notes either, as they're copy-paste noise from jd.md schema).
_STATUS_IGNORE = re.compile(
    r"^\s*-\s+\*\*(Compensation|Location|URL|Fetched|Employment):\*\*", re.IGNORECASE
)

# Regex to detect any bold-key bullet so we can identify unrecognized ones
_STATUS_BOLD_KEY_RE = re.compile(r"^\s*-\s+\*\*([^*]+):\*\*", re.IGNORECASE)


def parse_status(text: str) -> dict:
    """
    Parse a status.md file.

    Returns a dict with: stage, priority (int|None), last_action, next_step, notes,
    and unrecognized_keys (set[str] — bold-key bullets not in the known set and not
    in the ignore list; callers can aggregate these for reporting).

    The notes value captures:
    - Any H2/H3 body section that follows the leading bullet block.
    - Any unrecognized bold-key bullet (e.g. ``- **Fit:** ...``) and all lines
      below it, since these are freeform content not jd.md copy-paste noise.
    """
    result = {
        "stage": "Discovered",
        "priority": None,
        "last_action": None,
        "next_step": None,
        "notes": None,
        "unrecognized_keys": set(),
    }

    lines = text.splitlines()
    body_lines = []
    in_bullets = True  # We start in the bullet block at the top of the file

    for line in lines:
        # Skip the H1 title line
        if line.startswith("# "):
            continue

        if in_bullets:
            # Check if this is a structured bullet we care about
            matched = False
            for key, pattern in _STATUS_FIELDS.items():
                m = pattern.match(line)
                if m:
                    value = m.group(1).strip()
                    if key == "priority":
                        try:
                            result["priority"] = int(value)
                        except ValueError:
                            pass
                    else:
                        result[key] = value
                    matched = True
                    break

            if matched:
                continue

            # Ignore jd-type bullets that sometimes appear in status.md
            if _STATUS_IGNORE.match(line):
                continue

            # An H2/H3 header marks the start of the body section (e.g. ## Fit)
            if line.startswith("##"):
                in_bullets = False
                body_lines.append(line)
                continue

            # A blank line — stay in bullet-scanning mode
            if line.strip() == "":
                continue

            # Any other non-bullet line signals body has started
            if not line.strip().startswith("-"):
                in_bullets = False
                body_lines.append(line)
                continue

            # A bold-key bullet we don't recognise (e.g. - **Fit:** ..., - **Flags:**)
            # is freeform content — fall into body mode and include it plus everything
            # below it in notes.
            mk = _STATUS_BOLD_KEY_RE.match(line)
            if mk:
                key_name = mk.group(1).strip()
                result["unrecognized_keys"].add(key_name)
                in_bullets = False
                body_lines.append(line)
                continue

            # Truly unrecognized bullet with no bold key — include in body too.
            in_bullets = False
            body_lines.append(line)
        else:
            body_lines.append(line)

    notes = "\n".join(body_lines).strip() or None
    result["notes"] = notes
    return result


# ---------------------------------------------------------------------------
# jd.md parser
# ---------------------------------------------------------------------------

_JD_FIELDS = {
    "url": re.compile(r"^\s*-\s+\*\*URL:\*\*\s*(.+)$", re.IGNORECASE),
    "location": re.compile(r"^\s*-\s+\*\*Location:\*\*\s*(.+)$", re.IGNORECASE),
    "employment": re.compile(r"^\s*-\s+\*\*Employment:\*\*\s*(.+)$", re.IGNORECASE),
    "compensation_raw": re.compile(r"^\s*-\s+\*\*Compensation:\*\*\s*(.+)$", re.IGNORECASE),
    "fetched_at": re.compile(r"^\s*-\s+\*\*Fetched:\*\*\s*(.+)$", re.IGNORECASE),
}


def parse_jd(text: str) -> dict:
    """Parse key-value bullets from jd.md. Returns a dict with structured fields."""
    result = {k: None for k in _JD_FIELDS}
    for line in text.splitlines():
        for key, pattern in _JD_FIELDS.items():
            m = pattern.match(line)
            if m:
                result[key] = m.group(1).strip()
                break
    return result


# ---------------------------------------------------------------------------
# Compensation parser
# ---------------------------------------------------------------------------

#   Strategy: try to extract one or two dollar amounts from the string.
#   Each amount can be:
#     - plain integer:            170000  or  170,000
#     - integer + k/K:            170K    or  170k
#     - decimal + k/K:            143.2K
#   We look for the pattern:  $<amount1>  [separator]  [$]<amount2>
#   where separator can be – — - or just whitespace around a dash/em-dash.
#
#   We deliberately do NOT try to infer missing $ or K in the second token —
#   instead we handle the "$100-250K" case by noting that when only one $ is
#   present and both numbers are small (<= 999), both should be scaled by K.

# A single dollar amount preceded by $ (used to anchor the first token)
_FIRST = r"\$([\d,]+(?:\.\d+)?)\s*([kK])?"
# Second token (optional $)
_SECOND = r"\$?([\d,]+(?:\.\d+)?)\s*([kK])?"
# Separator between range endpoints: em dash, en dash, hyphen, or " - "
_SEP = r"\s*[–—\-]\s*"

_RANGE_RE = re.compile(
    rf"{_FIRST}{_SEP}{_SECOND}",
    re.IGNORECASE,
)
_SINGLE_RE = re.compile(
    r"\$([\d,]+(?:\.\d+)?)\s*([kK])?",
    re.IGNORECASE,
)


def _parse_amount(digits_str: str, k_suffix: str | None) -> int:
    """Convert a digit string (possibly with commas or decimal) + optional K to whole dollars."""
    # Remove commas
    cleaned = digits_str.replace(",", "")
    value = float(cleaned)
    if k_suffix:
        value *= 1000
    return int(round(value))


def parse_comp(raw: str | None) -> tuple[int | None, int | None]:
    """
    Parse a compensation string into (comp_low, comp_high) in whole dollars.

    Examples handled:
        "$100k–$250k"           → (100000, 250000)
        "$100-250K"             → (100000, 250000)   # second token inherits K
        "$150,000–$200,000"     → (150000, 200000)
        "$143.2K - $284K"       → (143200, 284000)
        "$174,250 - $205,000"   → (174250, 205000)
        "$170,000"              → (170000, None)
        "Not listed"            → (None, None)
        "Ask recruiter"         → (None, None)
        None / ""               → (None, None)
    """
    if not raw:
        return None, None

    text = raw.strip()
    if not text:
        return None, None

    # Explicit "not listed" variants
    if re.match(r"not\s+listed", text, re.IGNORECASE):
        return None, None

    # Try a range first
    m = _RANGE_RE.search(text)
    if m:
        d1, k1, d2, k2 = m.group(1), m.group(2), m.group(3), m.group(4)
        # K-inheritance rules for "$100-250K" style ranges:
        # If the first token has no K but the second does, and the first token
        # is a small number (≤ 999), then the first token also gets K.
        # e.g.  "$100-250K"  → k1=None, k2="K", d1=100 → low gets K too
        # Don't inherit when first token is already large (full dollar amount):
        # e.g.  "$150,000-200,000" → both are large; no K anywhere
        if not k1 and k2 and float(d1.replace(",", "")) <= 999:
            k1 = k2  # propagate K back to the first token
        low = _parse_amount(d1, k1)
        # Also propagate K forward: when first has K and second is small with no K
        # e.g.  "$100K - $250" where 250 is ambiguous — don't scale, leave as-is
        # (We only inherit forward if the second token is clearly in the K range)
        if not k2 and k1 and float(d2.replace(",", "")) <= 999:
            k2 = k1
        high = _parse_amount(d2, k2)
        return low, high

    # Try a single value
    m = _SINGLE_RE.search(text)
    if m:
        return _parse_amount(m.group(1), m.group(2)), None

    return None, None


# ---------------------------------------------------------------------------
# contacts.md parser
# ---------------------------------------------------------------------------

# Order matters: "semi-warm" must be checked before "warm" so substring matching
# doesn't accidentally classify "Semi-warm" sections as plain "warm".
_TIER_MAP = [
    ("semi-warm", "semi-warm"),
    ("semi warm", "semi-warm"),
    ("warm", "warm"),
    ("cold", "cold"),
]


def _tier_from_header(header_text: str) -> str | None:
    """Extract tier name from a section header like '## Warm' or '## Semi-warm'."""
    cleaned = header_text.strip().lstrip("#").strip().lower()
    # Strip emoji and punctuation (keep hyphens and word chars)
    cleaned = re.sub(r"[^\w\-]", " ", cleaned).strip()
    # _TIER_MAP is ordered so "semi-warm" is checked before "warm"
    for key, val in _TIER_MAP:
        if key in cleaned:
            return val
    return None


_H2_RE = re.compile(r"^##\s+(.+)$")
_H3_RE = re.compile(r"^###\s+(.+)$")
_BULLET_FIELD_RE = re.compile(r"^\s*-\s+\*\*(\w[\w ]+):\*\*\s*(.*)$")


def parse_contacts(text: str) -> list[dict]:
    """
    Parse contacts.md best-effort.

    Looks for ## <Tier> section headers and ### <Name> contact sub-headers, then
    extracts - **Field:** value bullets beneath each named contact.

    Any content that can't be attributed to a named contact is collected and
    returned as a single synthetic row with name="(unparsed notes)".

    Returns a list of contact dicts with keys: name, role, linkedin, email, tier, notes.
    """
    if not text.strip():
        return []

    contacts = []
    current_tier: str | None = None
    current_name: str | None = None
    current_fields: dict = {}
    unparsed_lines: list[str] = []

    def _flush_contact():
        nonlocal current_name, current_fields
        if current_name:
            contacts.append({
                "name": current_name,
                "role": current_fields.get("role"),
                "linkedin": current_fields.get("linkedin"),
                "email": current_fields.get("email"),
                "tier": current_tier,
                "notes": current_fields.get("notes"),
            })
        current_name = None
        current_fields = {}

    for line in text.splitlines():
        # H2 header → new tier section
        m_h2 = _H2_RE.match(line)
        if m_h2:
            _flush_contact()
            tier = _tier_from_header(m_h2.group(1))
            if tier:
                current_tier = tier
            continue

        # H3 header → new named contact
        m_h3 = _H3_RE.match(line)
        if m_h3:
            _flush_contact()
            current_name = m_h3.group(1).strip()
            continue

        # Bullet field beneath a named contact
        m_field = _BULLET_FIELD_RE.match(line)
        if m_field and current_name:
            key = m_field.group(1).strip().lower()
            val = m_field.group(2).strip()
            # Map common field names to canonical keys
            key_map = {
                "role": "role",
                "linkedin": "linkedin",
                "email": "email",
                "relationship": "notes",
                "notes": "notes",
            }
            canonical = key_map.get(key)
            if canonical:
                if canonical == "notes" and "notes" in current_fields:
                    current_fields["notes"] += "\n" + val
                else:
                    current_fields[canonical] = val
            continue

        # Continuation lines not matching any pattern — unparsed
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and current_name is None:
            unparsed_lines.append(line)

    _flush_contact()

    # Collect leftover unparsed content into a synthetic row
    unparsed_text = "\n".join(unparsed_lines).strip()
    if not contacts and unparsed_text:
        return [{"name": "(unparsed notes)", "role": None, "linkedin": None,
                 "email": None, "tier": None, "notes": unparsed_text}]

    return contacts


# ---------------------------------------------------------------------------
# YAML frontmatter parser
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
_FM_LINE_RE = re.compile(r"^(\w[\w-]*):\s*(.*)$")


def parse_frontmatter(text: str) -> dict:
    """
    Minimal inline YAML frontmatter parser.

    Only handles simple key: value lines (no nested YAML). Safe for the
    frontmatter shapes used in this project (persona, variant, target, etc.).
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        lm = _FM_LINE_RE.match(line.strip())
        if lm:
            fm[lm.group(1).strip()] = lm.group(2).strip()
    return fm


# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------

def open_db(db_path: pathlib.Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Core migration logic
# ---------------------------------------------------------------------------

def run_migration(
    memory_dir: pathlib.Path,
    db_path: pathlib.Path,
    report_path: pathlib.Path,
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    """
    Run the full migration.

    Returns a summary dict (same data written to the report). In dry_run mode,
    no DB or report files are written.
    """
    today = datetime.now(timezone.utc).date().isoformat()

    # ------------------------------------------------------------------
    # Guard: refuse to overwrite existing DB unless --force
    # ------------------------------------------------------------------
    if not dry_run and db_path.exists() and not force:
        print(
            f"ERROR: {db_path} already exists. Use --force to overwrite.",
            file=sys.stderr,
        )
        sys.exit(1)

    apps_dir = memory_dir / "applications"

    # ------------------------------------------------------------------
    # Parse index.md
    # ------------------------------------------------------------------
    index_path = apps_dir / "index.md"
    index_rows: list[dict] = []
    if index_path.exists():
        index_rows = parse_index(index_path.read_text(encoding="utf-8"))

    index_keys = {(r["company_slug"], r["role_slug"]): r for r in index_rows}

    # ------------------------------------------------------------------
    # Enumerate application folders on disk
    # ------------------------------------------------------------------
    # Format: applications/<company-slug>/<role-slug>/
    disk_roles: list[tuple[str, str]] = []  # (co_slug, role_slug)
    if apps_dir.is_dir():
        for co_dir in sorted(apps_dir.iterdir()):
            if co_dir.name.startswith("_") or co_dir.name.startswith("."):
                continue
            if not co_dir.is_dir():
                continue
            for role_dir in sorted(co_dir.iterdir()):
                if role_dir.name.startswith("_") or role_dir.name.startswith("."):
                    continue
                if not role_dir.is_dir():
                    continue
                disk_roles.append((co_dir.name, role_dir.name))

    disk_keys = set(disk_roles)

    # Classify
    index_only = set(index_keys.keys()) - disk_keys
    folder_only = disk_keys - set(index_keys.keys())

    # ------------------------------------------------------------------
    # Build the full set of application rows to insert
    # ------------------------------------------------------------------
    # (company_slug, role_slug) → row dict
    all_apps: dict[tuple[str, str], dict] = {}

    for key, row in index_keys.items():
        all_apps[key] = {
            "company_slug": row["company_slug"],
            "role_slug": row["role_slug"],
            "company": row["company"],
            "role": row["role"],
            "stage": row["stage"],
            "priority": None,
            "last_action": row["last_action"],
            "next_step": row["next_step"],
            "notes": None,
            "updated": row["updated"],
            "created_at": row["updated"] or today,
        }

    # Folder-only entries — create minimal row
    for co_slug, role_slug in folder_only:
        # Try to derive a display name from the slug
        company = co_slug.replace("-", " ").title()
        role = role_slug.replace("-", " ").title()
        all_apps[(co_slug, role_slug)] = {
            "company_slug": co_slug,
            "role_slug": role_slug,
            "company": company,
            "role": role,
            "stage": "Folder only",
            "priority": None,
            "last_action": None,
            "next_step": None,
            "notes": None,
            "updated": today,
            "created_at": today,
        }

    # ------------------------------------------------------------------
    # Parse per-role files and enrich app rows
    # ------------------------------------------------------------------
    jd_rows: list[dict] = []
    contact_rows: list[dict] = []  # keyed by (co_slug, role_slug) indirectly
    draft_rows: list[dict] = []

    # Tracking for the report
    comp_parse_failures: list[str] = []
    synthetic_contacts: list[str] = []
    role_failures: list[str] = []
    all_unrecognized_keys: set[str] = set()

    for co_slug, role_slug in disk_roles:
        key = (co_slug, role_slug)
        role_dir = apps_dir / co_slug / role_slug

        try:
            # --- status.md ---
            status_path = role_dir / "status.md"
            if status_path.exists():
                st = parse_status(status_path.read_text(encoding="utf-8"))
                row = all_apps[key]
                # status.md wins over index.md for structured fields, BUT we keep
                # the synthetic "Folder only" stage for folders that had no index row.
                is_folder_only = row["stage"] == "Folder only"
                if not is_folder_only:
                    # Accept any stage from status.md (even "Discovered" — it's explicit)
                    row["stage"] = st["stage"]
                if st["priority"] is not None:
                    row["priority"] = st["priority"]
                if st["last_action"]:
                    row["last_action"] = st["last_action"]
                if st["next_step"]:
                    row["next_step"] = st["next_step"]
                if st["notes"]:
                    row["notes"] = st["notes"]
                all_unrecognized_keys |= st["unrecognized_keys"]

            # --- jd.md ---
            jd_path = role_dir / "jd.md"
            if jd_path.exists():
                jd = parse_jd(jd_path.read_text(encoding="utf-8"))
                comp_raw = jd["compensation_raw"]
                comp_low, comp_high = parse_comp(comp_raw)
                if comp_raw and not re.match(r"not\s+listed", comp_raw, re.IGNORECASE) and comp_low is None:
                    comp_parse_failures.append(f"{co_slug}/{role_slug}: {comp_raw!r}")
                jd_rows.append({
                    "key": key,
                    "url": jd["url"],
                    "location": jd["location"],
                    "employment": jd["employment"],
                    "compensation_raw": comp_raw,
                    "comp_low": comp_low,
                    "comp_high": comp_high,
                    "fetched_at": jd["fetched_at"],
                    "body_path": str(jd_path.resolve()),
                })

            # --- contacts.md ---
            contacts_path = role_dir / "contacts.md"
            if contacts_path.exists():
                raw = contacts_path.read_text(encoding="utf-8")
                parsed = parse_contacts(raw)
                if any(c["name"] == "(unparsed notes)" for c in parsed):
                    synthetic_contacts.append(f"{co_slug}/{role_slug}")
                for c in parsed:
                    contact_rows.append({"key": key, **c})

            # --- drafts/*.md ---
            drafts_dir = role_dir / "drafts"
            if drafts_dir.is_dir():
                for draft_path in sorted(drafts_dir.glob("*.md")):
                    text = draft_path.read_text(encoding="utf-8")
                    fm = parse_frontmatter(text)

                    mtime = draft_path.stat().st_mtime
                    updated_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

                    draft_rows.append({
                        "key": key,
                        "path": str(draft_path.resolve()),
                        "name": draft_path.stem,
                        "persona": fm.get("persona"),
                        "variant": fm.get("variant"),
                        "target": fm.get("target"),
                        "updated_at": updated_at,
                    })

        except Exception as exc:
            role_failures.append(f"{co_slug}/{role_slug}: {exc}")

    # ------------------------------------------------------------------
    # Build summary
    # ------------------------------------------------------------------
    summary = {
        "total_applications": len(all_apps),
        "total_jd": len(jd_rows),
        "total_contacts": len(contact_rows),
        "total_drafts": len(draft_rows),
        "index_only": sorted(index_only),
        "folder_only": sorted(folder_only),
        "comp_parse_failures": comp_parse_failures,
        "synthetic_contacts": synthetic_contacts,
        "role_failures": role_failures,
        "unrecognized_status_keys": sorted(all_unrecognized_keys),
    }

    # ------------------------------------------------------------------
    # Print dry-run summary and bail
    # ------------------------------------------------------------------
    if dry_run:
        _print_summary(summary)
        return summary

    # ------------------------------------------------------------------
    # Write DB
    # ------------------------------------------------------------------
    if force and db_path.exists():
        db_path.unlink()

    conn = open_db(db_path)
    try:
        with conn:
            # applications
            for (co_slug, role_slug), app in all_apps.items():
                conn.execute(
                    """
                    INSERT INTO applications
                      (company_slug, role_slug, company, role, stage, priority,
                       last_action, next_step, notes, updated, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(company_slug, role_slug) DO UPDATE SET
                      stage = excluded.stage,
                      priority = excluded.priority,
                      last_action = excluded.last_action,
                      next_step = excluded.next_step,
                      notes = excluded.notes,
                      updated = excluded.updated
                    """,
                    (
                        app["company_slug"], app["role_slug"],
                        app["company"], app["role"],
                        app["stage"], app["priority"],
                        app["last_action"], app["next_step"],
                        app["notes"], app["updated"], app["created_at"],
                    ),
                )

            # Build a lookup: (co_slug, role_slug) → application id
            id_lookup: dict[tuple[str, str], int] = {}
            for row in conn.execute("SELECT id, company_slug, role_slug FROM applications"):
                id_lookup[(row["company_slug"], row["role_slug"])] = row["id"]

            # jd
            for jd in jd_rows:
                app_id = id_lookup.get(jd["key"])
                if app_id is None:
                    continue
                conn.execute(
                    """
                    INSERT OR REPLACE INTO jd
                      (application_id, url, location, employment,
                       compensation_raw, comp_low, comp_high, fetched_at, body_path)
                    VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        app_id, jd["url"], jd["location"], jd["employment"],
                        jd["compensation_raw"], jd["comp_low"], jd["comp_high"],
                        jd["fetched_at"], jd["body_path"],
                    ),
                )

            # contacts
            for c in contact_rows:
                app_id = id_lookup.get(c["key"])
                if app_id is None:
                    continue
                conn.execute(
                    """
                    INSERT INTO contacts
                      (application_id, name, role, linkedin, email, tier, notes)
                    VALUES (?,?,?,?,?,?,?)
                    """,
                    (app_id, c["name"], c["role"], c["linkedin"],
                     c["email"], c["tier"], c["notes"]),
                )

            # drafts
            for d in draft_rows:
                app_id = id_lookup.get(d["key"])
                if app_id is None:
                    continue
                conn.execute(
                    """
                    INSERT OR REPLACE INTO drafts
                      (application_id, path, name, persona, variant, target, updated_at)
                    VALUES (?,?,?,?,?,?,?)
                    """,
                    (app_id, d["path"], d["name"], d["persona"],
                     d["variant"], d["target"], d["updated_at"]),
                )

    finally:
        conn.close()

    # ------------------------------------------------------------------
    # Write report
    # ------------------------------------------------------------------
    _write_report(report_path, summary)
    _print_summary(summary)

    return summary


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _print_summary(s: dict) -> None:
    print(f"applications : {s['total_applications']}")
    print(f"jd           : {s['total_jd']}")
    print(f"contacts     : {s['total_contacts']}")
    print(f"drafts       : {s['total_drafts']}")
    if s["index_only"]:
        print(f"index-only   : {len(s['index_only'])} rows (no matching folder)")
    if s["folder_only"]:
        print(f"folder-only  : {len(s['folder_only'])} folders (not in index)")
    if s["comp_parse_failures"]:
        print(f"comp failures: {len(s['comp_parse_failures'])}")
    if s["synthetic_contacts"]:
        print(f"synthetic contacts: {len(s['synthetic_contacts'])}")
    if s["role_failures"]:
        print(f"role failures: {len(s['role_failures'])}")
    if s["unrecognized_status_keys"]:
        print(f"unrecognized status keys: {', '.join(s['unrecognized_status_keys'])}")


def _write_report(path: pathlib.Path, s: dict) -> None:
    lines = [
        "# Migration Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Totals",
        "",
        "| Table | Rows |",
        "|---|---|",
        f"| applications | {s['total_applications']} |",
        f"| jd | {s['total_jd']} |",
        f"| contacts | {s['total_contacts']} |",
        f"| drafts | {s['total_drafts']} |",
        "",
    ]

    if s["folder_only"]:
        lines += [
            "## Orphans — folder only (no index.md row)",
            "",
            "These folders exist on disk but had no matching row in index.md.",
            "They were inserted with `stage = 'Folder only'`.",
            "",
        ]
        for key in s["folder_only"]:
            lines.append(f"- `{key[0]}/{key[1]}`")
        lines.append("")

    if s["index_only"]:
        lines += [
            "## Orphans — index only (no matching folder)",
            "",
            "These rows exist in index.md but have no matching folder on disk.",
            "They were inserted as-is (no status/jd/contacts/drafts data).",
            "",
        ]
        for key in s["index_only"]:
            lines.append(f"- `{key[0]}/{key[1]}`")
        lines.append("")

    if s["comp_parse_failures"]:
        lines += [
            "## Compensation parse failures",
            "",
            "These JDs had a non-empty `Compensation` field that couldn't be parsed",
            "into `comp_low`/`comp_high`. The raw value is stored in `compensation_raw`.",
            "",
        ]
        for item in s["comp_parse_failures"]:
            lines.append(f"- {item}")
        lines.append("")

    if s["synthetic_contacts"]:
        lines += [
            "## Contacts — synthetic (unparsed) rows",
            "",
            "These contacts.md files couldn't be parsed into named contact rows.",
            "The full file content was stored in a synthetic `(unparsed notes)` row.",
            "",
        ]
        for item in s["synthetic_contacts"]:
            lines.append(f"- `{item}`")
        lines.append("")

    if s["role_failures"]:
        lines += [
            "## Role-level failures",
            "",
            "These roles threw an exception during parsing and were skipped.",
            "The application row (from index.md) was still inserted if present.",
            "",
        ]
        for item in s["role_failures"]:
            lines.append(f"- `{item}`")
        lines.append("")

    if s["unrecognized_status_keys"]:
        lines += [
            "## Unrecognized status.md bullet keys",
            "",
            "These bold-key bullets were not in the recognized set (`Stage`, `Priority`,",
            "`Last action`, `Next step`) and were folded into `notes` instead of being",
            "dropped. Promote any to first-class columns if needed.",
            "",
        ]
        for key in s["unrecognized_status_keys"]:
            lines.append(f"- `{key}`")
        lines.append("")

    if not any([
        s["folder_only"], s["index_only"],
        s["comp_parse_failures"], s["synthetic_contacts"],
        s["role_failures"], s["unrecognized_status_keys"],
    ]):
        lines += ["## No issues found", "", "All rows migrated cleanly.", ""]

    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate markdown application pipeline to SQLite."
    )
    parser.add_argument(
        "--memory-dir",
        type=pathlib.Path,
        default=None,
        help="Path to the memory/ directory (default: $PLYTOOLS_MEMORY_DIR)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing DB if present",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse everything and print summary; don't write DB or report",
    )
    args = parser.parse_args()

    memory_dir = (args.memory_dir if args.memory_dir is not None else default_memory_dir()).expanduser().resolve()
    db_path = memory_dir / "applications.db"
    report_path = memory_dir / "applications" / "_migration_report.md"

    run_migration(
        memory_dir=memory_dir,
        db_path=db_path,
        report_path=report_path,
        dry_run=args.dry_run,
        force=args.force,
    )


if __name__ == "__main__":
    main()
