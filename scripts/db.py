#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# ///
"""db.py — read/write the applications SQLite database.

Usage:
  uv run scripts/db.py upsert <company> <role> <stage> <last> <next> <updated>
  uv run scripts/db.py append  <company> <role> <stage> <last> <next> <updated>
  uv run scripts/db.py list
  uv run scripts/db.py reconcile <applications-dir>
  uv run scripts/db.py import-shortlist <shortlist.md> <applications-dir>

Flags (all subcommands):
  --db <path>           Override DB path (default: ~/.claude/.../memory/applications.db)

Flags (upsert / append only):
  --priority N          Set priority (integer). Omit to leave unchanged / NULL on insert.
  --clear-priority      Set priority to NULL regardless of --priority.
"""
from __future__ import annotations

import argparse
import datetime
import pathlib
import re
import sqlite3
import sys

import os


def default_db_path() -> pathlib.Path:
    """Resolve the SQLite path from $PLYTOOLS_MEMORY_DIR/applications.db.
    Explicit env var + no hardcoded personal path — callers without the env
    var set must pass --db."""
    env = os.environ.get("PLYTOOLS_MEMORY_DIR")
    if not env:
        sys.exit(
            "PLYTOOLS_MEMORY_DIR is not set and no --db path was provided.\n"
            "Set the env var to the directory containing applications.db, "
            "or pass --db <path>."
        )
    return pathlib.Path(env).expanduser() / "applications.db"

HEADERS = ["Company", "Role", "Stage", "Last action", "Next", "Updated"]
SHORTLIST_HEADERS = ["Company", "Role", "Location", "URL", "Reason", "Status"]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def open_db(db_path: pathlib.Path) -> sqlite3.Connection:
    if not db_path.exists():
        sys.exit(f"db not found: {db_path}\nRun: uv run scripts/migrate_to_sqlite.py")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


# ---------------------------------------------------------------------------
# Slug helpers — match viewer's slugify (src/lib/parsers.ts):
# `&` becomes `and` before non-alphanumeric runs collapse to hyphens.
# ---------------------------------------------------------------------------


def slugify(text: str) -> str:
    """Folder-safe slug. Matches the viewer's slugify (src/lib/parsers.ts):
    `&` becomes `and` before non-alphanumeric runs collapse to hyphens."""
    text = text.lower().strip()
    text = text.replace("&", "and")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def dedupe_role_slugs(roles: list[str]) -> dict[str, str]:
    """Deterministically map a list of role strings to collision-safe slugs.
    Repeat titles get `-2`, `-3` suffixes in list order."""
    from collections import defaultdict

    seen: dict[str, int] = defaultdict(int)
    out: dict[str, str] = {}
    for r in roles:
        base = slugify(r)
        seen[base] += 1
        out[r] = base if seen[base] == 1 else f"{base}-{seen[base]}"
    return out


# ---------------------------------------------------------------------------
# Table rendering (stdout)
# ---------------------------------------------------------------------------


def _header_line() -> str:
    return "| " + " | ".join(HEADERS) + " |"


def _separator_line() -> str:
    return "|" + "|".join(["---"] * len(HEADERS)) + "|"


def render_table(rows: list[dict]) -> str:
    """Render application rows as a markdown pipe table."""
    lines = [_header_line(), _separator_line()]
    for r in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    r["company"] or "",
                    r["role"] or "",
                    r["stage"] or "",
                    r["last_action"] or "",
                    r["next_step"] or "",
                    r["updated"] or "",
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Core DB operations
# ---------------------------------------------------------------------------


def upsert(
    conn: sqlite3.Connection,
    company: str,
    role: str,
    stage: str,
    last_action: str,
    next_step: str,
    updated: str,
    priority: int | None = None,
    clear_priority: bool = False,
) -> None:
    """Idempotent write keyed on (company_slug, role_slug).

    created_at is set on INSERT only and never touched on UPDATE.
    priority is updated only when explicitly passed or --clear-priority is set.
    """
    today = datetime.date.today().isoformat()
    co_slug = slugify(company)
    ro_slug = slugify(role)
    updated_val = updated or today

    existing = conn.execute(
        "SELECT id, created_at, priority FROM applications WHERE company_slug=? AND role_slug=?",
        (co_slug, ro_slug),
    ).fetchone()

    if existing is None:
        # INSERT
        new_priority = None if clear_priority else priority
        conn.execute(
            """
            INSERT INTO applications
              (company_slug, role_slug, company, role, stage,
               last_action, next_step, updated, created_at, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                co_slug,
                ro_slug,
                company,
                role,
                stage,
                last_action,
                next_step,
                updated_val,
                today,
                new_priority,
            ),
        )
    else:
        # UPDATE — preserve created_at; conditionally update priority
        if clear_priority:
            new_priority = None
        elif priority is not None:
            new_priority = priority
        else:
            new_priority = existing["priority"]

        conn.execute(
            """
            UPDATE applications
            SET company=?, role=?, stage=?, last_action=?, next_step=?, updated=?, priority=?
            WHERE company_slug=? AND role_slug=?
            """,
            (
                company,
                role,
                stage,
                last_action,
                next_step,
                updated_val,
                new_priority,
                co_slug,
                ro_slug,
            ),
        )
    conn.commit()


def list_rows(conn: sqlite3.Connection) -> list[dict]:
    """Return all application rows sorted by updated DESC, company, role."""
    rows = conn.execute(
        "SELECT company, role, stage, last_action, next_step, updated "
        "FROM applications "
        "ORDER BY updated DESC, company, role"
    ).fetchall()
    return [dict(r) for r in rows]


def reconcile(conn: sqlite3.Connection, apps_dir: pathlib.Path) -> None:
    """Scan <apps-dir>/<co>/<role>/ folders and ensure each has a DB row.

    status.md files are gone (retired in step 3). Any folder without a DB
    row gets inserted with stage='Folder only' so it surfaces in the index.
    """
    if not apps_dir.exists():
        return
    today = datetime.date.today().isoformat()
    for company_dir in sorted(apps_dir.iterdir()):
        if not company_dir.is_dir():
            continue
        if company_dir.name.startswith("_") or company_dir.name.startswith("."):
            continue
        for role_dir in sorted(company_dir.iterdir()):
            if not role_dir.is_dir():
                continue
            co_slug = company_dir.name
            ro_slug = role_dir.name
            existing = conn.execute(
                "SELECT id FROM applications WHERE company_slug=? AND role_slug=?",
                (co_slug, ro_slug),
            ).fetchone()
            if existing is None:
                # Derive human-readable company/role from slugs
                company = co_slug.replace("-", " ").title()
                role = ro_slug.replace("-", " ").title()
                conn.execute(
                    """
                    INSERT INTO applications
                      (company_slug, role_slug, company, role, stage,
                       last_action, next_step, updated, created_at)
                    VALUES (?, ?, ?, ?, 'Folder only', '—', 'Add to index', ?, ?)
                    """,
                    (co_slug, ro_slug, company, role, today, today),
                )
    conn.commit()


# ---------------------------------------------------------------------------
# Shortlist helpers
# ---------------------------------------------------------------------------


def read_shortlist(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    seen_header = False
    seen_sep = False
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            seen_header = False
            seen_sep = False
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) != len(SHORTLIST_HEADERS):
            print(f"WARN: skipping malformed shortlist row (expected 6 cells, got {len(cells)}): {stripped}", file=sys.stderr)
            continue
        if cells == SHORTLIST_HEADERS:
            seen_header = True
            continue
        if all(set(c) <= {"-", ":", " "} for c in cells):
            if seen_header:
                seen_sep = True
            continue
        if not (seen_header and seen_sep):
            continue
        rows.append(dict(zip(SHORTLIST_HEADERS, cells)))
    return rows


def _role_jd_stub(company: str, row: dict) -> str:
    lines = [f"# {company} — {row['Role']}", ""]
    lines.append(
        "_Stub. Full JD not yet fetched. Run job-apply Stage 1 on this role to fetch the description._"
    )
    lines.append("")
    if row.get("Location"):
        lines.append(f"- **Location:** {row['Location']}")
    if row.get("URL"):
        lines.append(f"- **URL:** {row['URL']}")
    return "\n".join(lines) + "\n"


def import_shortlist(
    conn: sqlite3.Connection,
    shortlist: pathlib.Path,
    apps_dir: pathlib.Path,
) -> dict:
    """Promote shortlist rows to the DB + create per-role stub folders.

    Never touches an existing (company, role) row — additive only.
    Skips rows whose Status is "dismissed".
    """
    today = datetime.date.today().isoformat()
    all_rows = read_shortlist(shortlist)
    rows = [r for r in all_rows if r["Status"] != "dismissed"]

    # Existing (company_slug, role_slug) pairs — skip to avoid downgrading progress.
    existing_pairs: set[tuple[str, str]] = set()
    for erow in conn.execute("SELECT company_slug, role_slug FROM applications").fetchall():
        existing_pairs.add((erow["company_slug"], erow["role_slug"]))

    by_company: dict[str, list[dict]] = {}
    for r in rows:
        by_company.setdefault(r["Company"], []).append(r)

    imported_rows = 0
    skipped_already_indexed = 0
    created_folders = 0
    preserved_folders = 0

    for company, company_rows in by_company.items():
        company_slug = slugify(company)
        company_dir = apps_dir / company_slug
        company_dir.mkdir(parents=True, exist_ok=True)

        role_map = dedupe_role_slugs([r["Role"] for r in company_rows])

        for r in company_rows:
            role_slug = role_map[r["Role"]]
            role_dir = company_dir / role_slug
            role_dir.mkdir(parents=True, exist_ok=True)
            jd_path = role_dir / "jd.md"
            if jd_path.exists():
                preserved_folders += 1
            else:
                jd_path.write_text(_role_jd_stub(company, r))
                created_folders += 1

            if (company_slug, role_slug) in existing_pairs:
                skipped_already_indexed += 1
                continue

            conn.execute(
                """
                INSERT INTO applications
                  (company_slug, role_slug, company, role, stage,
                   last_action, next_step, updated, created_at)
                VALUES (?, ?, ?, ?, 'Discovered', 'Shortlisted', 'Ingest JD + contacts', ?, ?)
                """,
                (company_slug, role_slug, company, r["Role"], today, today),
            )
            existing_pairs.add((company_slug, role_slug))
            imported_rows += 1

    conn.commit()

    return {
        "imported_rows": imported_rows,
        "skipped_already_indexed": skipped_already_indexed,
        "created_stubs": created_folders,
        "preserved_existing_jds": preserved_folders,
        "dismissed_skipped": sum(1 for r in all_rows if r["Status"] == "dismissed"),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Read/write the applications SQLite database."
    )
    parser.add_argument(
        "--db",
        type=pathlib.Path,
        default=None,
        help="Path to applications.db (default: $PLYTOOLS_MEMORY_DIR/applications.db)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # upsert
    p_upsert = sub.add_parser("upsert", help="Upsert a row by (company, role)")
    p_upsert.add_argument("company")
    p_upsert.add_argument("role")
    p_upsert.add_argument("stage")
    p_upsert.add_argument("last")
    p_upsert.add_argument("next")
    p_upsert.add_argument("updated")
    p_upsert.add_argument("--priority", type=int, default=None)
    p_upsert.add_argument(
        "--clear-priority", action="store_true", help="Set priority to NULL"
    )

    # append (alias of upsert — same behavior, both names supported)
    p_append = sub.add_parser(
        "append", help="Alias for upsert; works whether the row exists or not"
    )
    p_append.add_argument("company")
    p_append.add_argument("role")
    p_append.add_argument("stage")
    p_append.add_argument("last")
    p_append.add_argument("next")
    p_append.add_argument("updated")
    p_append.add_argument("--priority", type=int, default=None)
    p_append.add_argument("--clear-priority", action="store_true")

    # list
    sub.add_parser("list", help="Print current applications table as markdown")

    # reconcile
    p_reconcile = sub.add_parser(
        "reconcile",
        help="Scan <apps-dir> folders and insert missing DB rows",
    )
    p_reconcile.add_argument("apps_dir", type=pathlib.Path)

    # import-shortlist
    p_import = sub.add_parser(
        "import-shortlist",
        help="Promote shortlist rows to the DB and create stub folders",
    )
    p_import.add_argument("shortlist", type=pathlib.Path)
    p_import.add_argument("apps_dir", type=pathlib.Path)

    args = parser.parse_args(argv)

    db_path = args.db if args.db is not None else default_db_path()
    conn = open_db(db_path)

    if args.cmd in ("upsert", "append"):
        upsert(
            conn,
            company=args.company,
            role=args.role,
            stage=args.stage,
            last_action=args.last,
            next_step=args.next,
            updated=args.updated,
            priority=args.priority,
            clear_priority=args.clear_priority,
        )
        print(render_table(list_rows(conn)), end="")
        return 0

    if args.cmd == "list":
        print(render_table(list_rows(conn)), end="")
        return 0

    if args.cmd == "reconcile":
        reconcile(conn, args.apps_dir)
        print(render_table(list_rows(conn)), end="")
        return 0

    if args.cmd == "import-shortlist":
        summary = import_shortlist(conn, args.shortlist, args.apps_dir)
        print(render_table(list_rows(conn)), end="")
        print()
        print(f"imported: {summary['imported_rows']} rows")
        print(f"skipped (already indexed): {summary['skipped_already_indexed']}")
        print(f"stubs created: {summary['created_stubs']}")
        print(f"existing jds preserved: {summary['preserved_existing_jds']}")
        print(f"dismissed rows skipped: {summary['dismissed_skipped']}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
