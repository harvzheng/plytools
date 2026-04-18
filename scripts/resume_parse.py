#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.27",
#     "pypdf>=4.0",
# ]
# ///
"""resume_parse.py — extract text + coarse sections from a resume PDF."""
from __future__ import annotations

import argparse
import io
import json
import pathlib
import sys
from typing import Any

import httpx
import pypdf

SECTION_HEADINGS = (
    "Experience",
    "Work Experience",
    "Employment",
    "Education",
    "Skills",
    "Projects",
    "Awards",
    "Summary",
    "Objective",
)


def _extract_text(pdf_bytes: bytes) -> str:
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    pages = [p.extract_text() or "" for p in reader.pages]
    return "\n".join(pages)


def _split_sections(text: str) -> dict[str, str]:
    """Heuristic: split into named sections based on headings on their own line."""
    lines = text.splitlines()
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        stripped = line.strip()
        matched = next((h for h in SECTION_HEADINGS if stripped.lower() == h.lower()), None)
        if matched:
            current = matched
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items() if v or k in sections}


def parse_resume_bytes(pdf_bytes: bytes) -> dict[str, Any]:
    raw = _extract_text(pdf_bytes)
    return {"raw_text": raw, "sections": _split_sections(raw)}


def parse_resume(src: str, client: httpx.Client | None = None) -> dict[str, Any]:
    if src.startswith("http://") or src.startswith("https://"):
        owns_client = client is None
        client = client or httpx.Client(follow_redirects=True, timeout=20.0)
        try:
            r = client.get(src)
            r.raise_for_status()
            return parse_resume_bytes(r.content)
        finally:
            if owns_client:
                client.close()
    path = pathlib.Path(src)
    return parse_resume_bytes(path.read_bytes())


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("src", help="URL or local path to PDF")
    args = parser.parse_args(argv)
    result = parse_resume(args.src)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
