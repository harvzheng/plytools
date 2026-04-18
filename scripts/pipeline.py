#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# ///
"""pipeline.py — read/append the applications/index.md markdown table.

Usage:
  uv run scripts/pipeline.py append <index.md> <company> <role> <stage> <last> <next> <updated>
  uv run scripts/pipeline.py list <index.md>
"""
from __future__ import annotations

import argparse
import pathlib
import sys
from dataclasses import asdict, dataclass, fields

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


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_add = sub.add_parser("append")
    p_add.add_argument("path", type=pathlib.Path)
    for f in fields(Row):
        p_add.add_argument(f.name)
    p_list = sub.add_parser("list")
    p_list.add_argument("path", type=pathlib.Path)

    args = parser.parse_args(argv)
    if args.cmd == "append":
        row = Row(**{f.name: getattr(args, f.name) for f in fields(Row)})
        append_row(args.path, row)
        print(render_index(read_index(args.path)), end="")
        return 0
    if args.cmd == "list":
        print(render_index(read_index(args.path)), end="")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
