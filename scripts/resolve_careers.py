#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""resolve_careers.py — company name → careers URL, with persistent CSV cache.

Usage:
  uv run scripts/resolve_careers.py <company> [--cache <path>]
  uv run scripts/resolve_careers.py --cache <path> --record <company> <careers_url> <ats> <source>

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

# Probe the JSON API endpoints (not the marketing pages). The marketing pages
# do soft-404s: Ashby's jobs.ashbyhq.com/<anything> returns 200, and
# boards.greenhouse.io/<anything> returns a 301 to a generic board-not-found
# page. The API endpoints return a real 404 for bad slugs.
# careers_url in the cache is the human-facing URL that fetch_jobs.py understands.
ATS_PROBES = [
    ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=false",
     "https://boards.greenhouse.io/{slug}"),
    ("lever", "https://api.lever.co/v0/postings/{slug}?mode=json",
     "https://jobs.lever.co/{slug}"),
    ("ashby", "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=false",
     "https://jobs.ashbyhq.com/{slug}"),
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
    cache_path: pathlib.Path | None = None,
    client: httpx.Client | None = None,
) -> dict:
    slug = slug_for(company)
    today = datetime.date.today().isoformat()

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

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=10.0, follow_redirects=False)
    try:
        for ats, probe_tpl, public_tpl in ATS_PROBES:
            probe_url = probe_tpl.format(slug=slug)
            try:
                r = client.get(probe_url)
            except httpx.HTTPError:
                continue
            if 200 <= r.status_code < 300:
                public_url = public_tpl.format(slug=slug)
                if cache_path is not None:
                    write_cache_row(cache_path, CacheRow(
                        company=company, slug=slug, careers_url=public_url,
                        ats=ats, source="probe", resolved_at=today,
                    ))
                return {
                    "company": company, "slug": slug, "careers_url": public_url,
                    "ats": ats, "source": "probe", "resolved_at": today,
                }
    finally:
        if owns_client:
            client.close()

    return {
        "company": company, "slug": slug, "careers_url": None,
        "ats": None, "source": "needs_google_or_manual", "resolved_at": today,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=pathlib.Path, default=None)
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
    result = resolve(company, cache_path=ns.cache)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
