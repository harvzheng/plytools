#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# ///
"""shortlist.py — read/append/status-update the per-run role shortlist markdown table.

Usage:
  uv run scripts/shortlist.py append <file> <company> <role> <location> <url> <reason> [--status <s>]
  uv run scripts/shortlist.py list <file>
  uv run scripts/shortlist.py set-status <file> <row-index> <approved|dismissed>
"""
from __future__ import annotations

import argparse
import pathlib
import sys
from dataclasses import dataclass, fields

HEADERS = ["Company", "Role", "Location", "URL", "Reason", "Status"]


@dataclass
class Row:
    company: str
    role: str
    location: str
    url: str
    reason: str
    status: str  # pending | approved | dismissed


def _header_line() -> str:
    return "| " + " | ".join(HEADERS) + " |"


def _separator_line() -> str:
    return "|" + "|".join(["---"] * len(HEADERS)) + "|"


def render_shortlist(rows: list[Row]) -> str:
    lines = [_header_line(), _separator_line()]
    for r in rows:
        lines.append(
            "| " + " | ".join([r.company, r.role, r.location, r.url, r.reason, r.status]) + " |"
        )
    return "\n".join(lines) + "\n"


def read_shortlist(path: pathlib.Path) -> list[Row]:
    if not path.exists():
        return []
    rows: list[Row] = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if cells == HEADERS or all(set(c) <= {"-", ":", " "} for c in cells):
            continue
        if len(cells) != len(HEADERS):
            continue
        rows.append(Row(*cells))
    return rows


def append_row(path: pathlib.Path, row: Row) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = read_shortlist(path)
    rows.append(row)
    path.write_text(render_shortlist(rows))


def set_status(path: pathlib.Path, row_index: int, status: str) -> None:
    if status not in {"pending", "approved", "dismissed"}:
        raise ValueError(f"invalid status: {status}")
    rows = read_shortlist(path)
    if row_index < 0 or row_index >= len(rows):
        raise IndexError(f"row {row_index} out of range (have {len(rows)} rows)")
    rows[row_index].status = status
    path.write_text(render_shortlist(rows))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("append")
    p_add.add_argument("path", type=pathlib.Path)
    for f in fields(Row):
        if f.name == "status":
            p_add.add_argument("--status", default="pending")
        else:
            p_add.add_argument(f.name)

    p_list = sub.add_parser("list")
    p_list.add_argument("path", type=pathlib.Path)

    p_set = sub.add_parser("set-status")
    p_set.add_argument("path", type=pathlib.Path)
    p_set.add_argument("row_index", type=int)
    p_set.add_argument("status")

    args = parser.parse_args(argv)
    if args.cmd == "append":
        kwargs = {f.name: getattr(args, f.name) for f in fields(Row)}
        append_row(args.path, Row(**kwargs))
        print(render_shortlist(read_shortlist(args.path)), end="")
        return 0
    if args.cmd == "list":
        print(render_shortlist(read_shortlist(args.path)), end="")
        return 0
    if args.cmd == "set-status":
        set_status(args.path, args.row_index, args.status)
        print(render_shortlist(read_shortlist(args.path)), end="")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
