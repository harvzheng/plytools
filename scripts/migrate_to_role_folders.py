#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# ///
# RETIRED: one-time migration script from a pre-role-folder era. Do not run again.
# Left in place for historical reference. pipeline.py (which it imported) is also
# retired — use scripts/db.py for all current pipeline operations.
"""One-shot migration from `applications/<company>/` to
`applications/<company>/<role-slug>/`.

Walks `applications/index.md` and, for each (company, role) row:

  1. Creates `<company-slug>/<role-slug>/` under the apps dir.
  2. If the company folder has real content (status.md, contacts.md, drafts/,
     or a non-stub jd.md), relocates it into the matched role subfolder — the
     one whose role string matches the populated status.md's H1/Role bullet.
  3. For every other role, writes a minimal per-role jd.md stub populated
     from the location/URL columns of the old company-level stub jd.md.
  4. Deletes the company-level stub jd.md once all role subfolders exist.

Role-slug collisions within a company (e.g., two "Sr. Product Designer" rows
in different cities) are broken by appending `-2`, `-3`, etc. in index-order.

Default is dry-run. Pass `--apply` to touch the filesystem.

Usage:
  uv run scripts/migrate_to_role_folders.py <apps_dir> [--apply]
"""
from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass

INDEX_HEADERS = ["Company", "Role", "Stage", "Last action", "Next", "Updated"]


def slugify(text: str) -> str:
    """Matches the viewer's slugify in src/lib/parsers.ts — `&` becomes `and`
    before non-alphanumeric runs collapse to hyphens. pipeline.py's older
    slugify strips `&` outright, which produces different folder names for
    companies like W&B; align on the viewer's rule here."""
    text = text.lower().strip()
    text = text.replace("&", "and")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text


@dataclass
class IndexRow:
    company: str
    role: str


def read_index(path: pathlib.Path) -> list[IndexRow]:
    rows: list[IndexRow] = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if cells == INDEX_HEADERS:
            continue
        if all(set(c) <= {"-", ":", " "} for c in cells):
            continue
        if len(cells) != len(INDEX_HEADERS):
            continue
        rows.append(IndexRow(company=cells[0], role=cells[1]))
    return rows


def parse_stub_jd(text: str) -> dict[str, tuple[str, str]]:
    """Parse a `pipeline.py import-shortlist` stub and return {role: (loc, url)}.

    Empty dict if the file isn't a recognizable stub."""
    if "shortlisted roles" not in text.lower():
        return {}
    out: dict[str, tuple[str, str]] = {}
    in_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            in_table = False
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) != 3:
            continue
        if cells == ["Role", "Location", "URL"]:
            in_table = True
            continue
        if all(set(c) <= {"-", ":", " "} for c in cells):
            continue
        if not in_table:
            continue
        role, loc, url = cells
        out[role] = (loc, url)
    return out


def parse_status_role(text: str) -> str | None:
    """Extract role from a status.md — prefer the `- **Role:**` bullet,
    fall back to the H1 `# Company — Role` shape."""
    for line in text.splitlines():
        m = re.match(r"^[-*]\s+\*\*Role:\*\*\s*(.+)$", line.strip())
        if m:
            return m.group(1).strip()
    for line in text.splitlines():
        if not line.startswith("# "):
            continue
        m = re.match(
            r"^#\s+(?:Status\s*[—\-]\s*)?(.+?)\s*[—\-]\s*(.+)$",
            line.strip(),
        )
        if m:
            return m.group(2).strip()
        break
    return None


def dedupe_role_slugs(roles: list[str]) -> dict[str, str]:
    """Turn a list of role strings into unique role-slugs, appending -2, -3
    on collisions in index order."""
    seen: dict[str, int] = defaultdict(int)
    out: dict[str, str] = {}
    for r in roles:
        base = slugify(r)
        seen[base] += 1
        out[r] = base if seen[base] == 1 else f"{base}-{seen[base]}"
    return out


def match_role(target: str, candidates: list[str]) -> str | None:
    """Best-effort match of a free-form status role string to an indexed role."""
    if target in candidates:
        return target
    t = slugify(target)
    for c in candidates:
        if slugify(c) == t:
            return c
    for c in candidates:
        if c.lower().startswith(target.lower()) or target.lower().startswith(c.lower()):
            return c
    return None


def minimal_role_jd(company: str, role: str, location: str, url: str) -> str:
    lines = [f"# {company} — {role}", ""]
    lines.append(
        "_Stub. Full JD not yet fetched. Run job-apply Stage 1 on this role to fetch the description._"
    )
    lines.append("")
    if location:
        lines.append(f"- **Location:** {location}")
    if url:
        lines.append(f"- **URL:** {url}")
    return "\n".join(lines) + "\n"


def migrate(apps_dir: pathlib.Path, index_path: pathlib.Path, apply: bool) -> int:
    rows = read_index(index_path)
    by_company: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        if r.role not in by_company[r.company]:
            by_company[r.company].append(r.role)

    actions: list[str] = []

    for company, roles in by_company.items():
        company_slug = slugify(company)
        folder = apps_dir / company_slug
        if not folder.is_dir():
            actions.append(f"SKIP: {company_slug}/ — not on disk (index-only)")
            # Still create subfolders so the model is consistent.
            if apply:
                folder.mkdir(parents=True, exist_ok=True)

        role_map = dedupe_role_slugs(roles)

        top_jd = folder / "jd.md"
        top_status = folder / "status.md"
        top_contacts = folder / "contacts.md"
        top_drafts = folder / "drafts"

        stub_table: dict[str, tuple[str, str]] = {}
        jd_is_stub = True
        if top_jd.exists():
            jd_text = top_jd.read_text()
            stub_table = parse_stub_jd(jd_text)
            jd_is_stub = bool(stub_table) or "shortlisted roles" in jd_text.lower()

        populated_role: str | None = None
        if top_status.exists():
            raw = parse_status_role(top_status.read_text())
            if raw:
                matched = match_role(raw, roles)
                if matched:
                    populated_role = matched
                else:
                    actions.append(
                        f"WARN: {company_slug}/status.md role '{raw}' doesn't match any indexed role; leaving in place"
                    )

        for role in roles:
            rslug = role_map[role]
            target = folder / rslug
            if target.exists():
                actions.append(f"EXISTS: {company_slug}/{rslug}/")
            else:
                actions.append(f"MKDIR:  {company_slug}/{rslug}/")
                if apply:
                    target.mkdir(parents=True, exist_ok=True)

            target_jd = target / "jd.md"
            if target_jd.exists():
                actions.append(f"EXISTS: {company_slug}/{rslug}/jd.md")
                continue

            if role == populated_role and top_jd.exists() and not jd_is_stub:
                actions.append(f"MOVE:   {company_slug}/jd.md -> {company_slug}/{rslug}/jd.md")
                if apply:
                    shutil.move(str(top_jd), str(target_jd))
            else:
                loc, url = stub_table.get(role, ("", ""))
                content = minimal_role_jd(company, role, loc, url)
                actions.append(f"WRITE:  {company_slug}/{rslug}/jd.md ({len(content)}B)")
                if apply:
                    target_jd.write_text(content)

        if populated_role:
            matched_folder = folder / role_map[populated_role]
            for src, name in [(top_status, "status.md"), (top_contacts, "contacts.md")]:
                if not src.exists():
                    continue
                dst = matched_folder / name
                if dst.exists():
                    actions.append(f"EXISTS: {company_slug}/{role_map[populated_role]}/{name}")
                    continue
                actions.append(
                    f"MOVE:   {company_slug}/{name} -> {company_slug}/{role_map[populated_role]}/{name}"
                )
                if apply:
                    shutil.move(str(src), str(dst))
            if top_drafts.is_dir():
                dst = matched_folder / "drafts"
                if dst.exists():
                    actions.append(f"EXISTS: {company_slug}/{role_map[populated_role]}/drafts/")
                else:
                    actions.append(
                        f"MOVE:   {company_slug}/drafts/ -> {company_slug}/{role_map[populated_role]}/drafts/"
                    )
                    if apply:
                        shutil.move(str(top_drafts), str(dst))

        if top_jd.exists() and jd_is_stub:
            actions.append(f"DELETE: {company_slug}/jd.md (stub)")
            if apply:
                top_jd.unlink()

    for a in actions:
        print(a)

    mode = "APPLIED" if apply else "DRY RUN"
    print(f"\n{mode}: {len(actions)} actions across {len(by_company)} companies")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("apps_dir", type=pathlib.Path)
    parser.add_argument(
        "--index",
        type=pathlib.Path,
        default=None,
        help="Defaults to <apps_dir>/index.md",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    index_path = args.index or (args.apps_dir / "index.md")
    return migrate(args.apps_dir, index_path, args.apply)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
