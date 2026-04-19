#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""resolve_careers.py — company name → careers URL, with persistent CSV cache.

Usage:
  uv run scripts/resolve_careers.py <company> [--linkedin <url>] [--cache <path>]
  uv run scripts/resolve_careers.py --record <company> <careers_url> <ats> <source> [--cache <path>]

Emits JSON on stdout.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import pathlib
import re
import sys
from dataclasses import dataclass, asdict

import httpx

ATS_PROBES = [
    ("greenhouse", "https://boards.greenhouse.io/{slug}"),
    ("greenhouse", "https://job-boards.greenhouse.io/{slug}"),
    ("lever", "https://jobs.lever.co/{slug}"),
    ("ashby", "https://jobs.ashbyhq.com/{slug}"),
]

CACHE_HEADERS = ["company", "slug", "careers_url", "ats", "source", "resolved_at"]


@dataclass
class CacheRow:
    company: str
    slug: str
    careers_url: str | None
    ats: str | None
    source: str  # probe | google | manual | unresolved
    resolved_at: str


def slug_for(company: str) -> str:
    return re.sub(r"[^a-z0-9]", "", company.lower())


def read_cache(path: pathlib.Path) -> list[CacheRow]:
    if not path.exists():
        return []
    rows: list[CacheRow] = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(CacheRow(
                company=r["company"],
                slug=r["slug"],
                careers_url=r["careers_url"] or None,
                ats=r["ats"] or None,
                source=r["source"],
                resolved_at=r["resolved_at"],
            ))
    return rows


def write_cache_row(path: pathlib.Path, row: CacheRow) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CACHE_HEADERS)
        if not existed:
            writer.writeheader()
        writer.writerow({
            "company": row.company,
            "slug": row.slug,
            "careers_url": row.careers_url or "",
            "ats": row.ats or "",
            "source": row.source,
            "resolved_at": row.resolved_at,
        })


def resolve(
    company: str,
    *,
    linkedin_url: str | None = None,
    cache_path: pathlib.Path | None = None,
    client: httpx.Client | None = None,
) -> dict:
    slug = slug_for(company)
    if cache_path is not None:
        for row in read_cache(cache_path):
            if row.slug == slug:
                return {
                    "company": row.company,
                    "slug": row.slug,
                    "careers_url": row.careers_url,
                    "ats": row.ats,
                    "source": row.source,
                    "resolved_at": row.resolved_at,
                }
    # Probe path implemented in Task 8.
    return {
        "company": company,
        "slug": slug,
        "careers_url": None,
        "ats": None,
        "source": "needs_google_or_manual",
        "resolved_at": datetime.date.today().isoformat(),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=pathlib.Path, default=None)
    parser.add_argument("--linkedin", default=None)
    parser.add_argument("--record", action="store_true")
    parser.add_argument("args", nargs="+")

    ns = parser.parse_args(argv)
    if ns.record:
        # <company> <careers_url> <ats> <source>
        if len(ns.args) != 4:
            print(json.dumps({"error": "record requires 4 args: company careers_url ats source"}))
            return 1
        company, url, ats, source = ns.args
        row = CacheRow(
            company=company,
            slug=slug_for(company),
            careers_url=url,
            ats=ats,
            source=source,
            resolved_at=datetime.date.today().isoformat(),
        )
        if ns.cache is None:
            print(json.dumps({"error": "--cache required with --record"}))
            return 1
        write_cache_row(ns.cache, row)
        print(json.dumps(asdict(row)))
        return 0
    company = ns.args[0]
    result = resolve(company, linkedin_url=ns.linkedin, cache_path=ns.cache)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
