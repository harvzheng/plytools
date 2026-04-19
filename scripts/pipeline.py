#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# ///
"""pipeline.py — read/append/upsert the applications/index.md markdown table.

Usage:
  uv run scripts/pipeline.py append <index.md> <company> <role> <stage> <last> <next> <updated>
  uv run scripts/pipeline.py upsert <index.md> <company> <role> <stage> <last> <next> <updated>
  uv run scripts/pipeline.py list <index.md>
  uv run scripts/pipeline.py reconcile <index.md> <applications-dir>
"""
from __future__ import annotations

import argparse
import datetime
import pathlib
import re
import sys
from dataclasses import dataclass, fields

HEADERS = ["Company", "Role", "Stage", "Last action", "Next", "Updated"]


@dataclass
class Row:
    company: str
    role: str
    stage: str
    last_action: str
    next_step: str
    updated: str


def _header_line() -> str:
    return "| " + " | ".join(HEADERS) + " |"


def _separator_line() -> str:
    return "|" + "|".join(["---"] * len(HEADERS)) + "|"


def render_index(rows: list[Row]) -> str:
    lines = [_header_line(), _separator_line()]
    for r in rows:
        lines.append("| " + " | ".join([r.company, r.role, r.stage, r.last_action, r.next_step, r.updated]) + " |")
    return "\n".join(lines) + "\n"


def read_index(path: pathlib.Path) -> list[Row]:
    if not path.exists():
        return []
    rows: list[Row] = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        # Skip header + separator
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if cells == HEADERS or all(set(c) <= {"-", ":", " "} for c in cells):
            continue
        if len(cells) != len(HEADERS):
            continue
        rows.append(Row(*cells))
    return rows


def append_row(path: pathlib.Path, row: Row) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = read_index(path)
    rows.append(row)
    path.write_text(render_index(rows))


def upsert_row(path: pathlib.Path, row: Row) -> None:
    """Insert row, or replace the existing row that matches (company, role)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = read_index(path)
    for i, existing in enumerate(rows):
        if existing.company == row.company and existing.role == row.role:
            rows[i] = row
            path.write_text(render_index(rows))
            return
    rows.append(row)
    path.write_text(render_index(rows))


def _parse_status_md(text: str, folder_name: str) -> Row:
    """Extract Row fields from a status.md file."""
    lines = text.splitlines()

    company = ""
    role = ""
    h1_right = ""

    # Try H1 line
    for line in lines:
        m = re.match(r"^#\s+(?:Status\s*[—\-]\s*)?([^—\-]+?)(?:\s*[—\-]\s*(.+))?$", line.strip())
        if m:
            h1_left = m.group(1).strip()
            h1_right = (m.group(2) or "").strip()
            if h1_right:
                company = h1_left
                role = h1_right
            else:
                company = h1_left
            break

    # Bold-key bullets
    stage = "Discovered"
    last_action = "—"
    next_step = "review"
    role_override = ""

    for line in lines:
        bm = re.match(r"^[-*]\s+\*\*(.+?):\*\*\s*(.+)$", line.strip())
        if not bm:
            continue
        key, val = bm.group(1).strip(), bm.group(2).strip()
        if key == "Stage":
            stage = val
        elif key == "Role":
            role_override = val
        elif key == "Last action":
            last_action = val
        elif key == "Next step":
            next_step = val

    if role_override:
        # Truncate at first " — " or comma
        role = re.split(r"\s*[—\-]\s*|,\s*", role_override, maxsplit=1)[0].strip()

    # Fix up company: if it looks like "Stainless, Product Designer" (comma-separated pair from
    # H1 like "# Status — Stainless, Product Designer"), strip everything after the first comma.
    # If role wasn't already set, take the trailing chunk as the role.
    if "," in company and not h1_right:
        parts = [p.strip() for p in company.split(",", 1)]
        company = parts[0]
        if not role and len(parts) > 1:
            role = parts[1]

    # Fallback to folder name
    if not company:
        company = folder_name.replace("-", " ").replace("_", " ").title()

    updated = datetime.date.today().isoformat()
    return Row(
        company=company,
        role=role or "—",
        stage=stage,
        last_action=last_action,
        next_step=next_step,
        updated=updated,
    )


def reconcile(index: pathlib.Path, apps_dir: pathlib.Path) -> None:
    """Scan apps_dir for subdirs with status.md and upsert each into index."""
    if not apps_dir.exists():
        return
    for subdir in sorted(apps_dir.iterdir()):
        if not subdir.is_dir():
            continue
        if subdir.name.startswith("_") or subdir.name.startswith("."):
            continue
        status_file = subdir / "status.md"
        if not status_file.exists():
            continue
        row = _parse_status_md(status_file.read_text(), subdir.name)
        upsert_row(index, row)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("append")
    p_add.add_argument("path", type=pathlib.Path)
    for f in fields(Row):
        p_add.add_argument(f.name)

    p_upsert = sub.add_parser("upsert")
    p_upsert.add_argument("path", type=pathlib.Path)
    for f in fields(Row):
        p_upsert.add_argument(f.name)

    p_list = sub.add_parser("list")
    p_list.add_argument("path", type=pathlib.Path)

    p_reconcile = sub.add_parser("reconcile")
    p_reconcile.add_argument("path", type=pathlib.Path)
    p_reconcile.add_argument("apps_dir", type=pathlib.Path)

    args = parser.parse_args(argv)
    if args.cmd == "append":
        row = Row(**{f.name: getattr(args, f.name) for f in fields(Row)})
        append_row(args.path, row)
        print(render_index(read_index(args.path)), end="")
        return 0
    if args.cmd == "upsert":
        row = Row(**{f.name: getattr(args, f.name) for f in fields(Row)})
        upsert_row(args.path, row)
        print(render_index(read_index(args.path)), end="")
        return 0
    if args.cmd == "list":
        print(render_index(read_index(args.path)), end="")
        return 0
    if args.cmd == "reconcile":
        reconcile(args.path, args.apps_dir)
        print(render_index(read_index(args.path)), end="")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
