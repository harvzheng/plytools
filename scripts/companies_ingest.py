#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "beautifulsoup4>=4.12"]
# ///
"""companies_ingest.py — ingest companies from a CSV or article URL.

Usage:
  uv run scripts/companies_ingest.py csv <path>
  uv run scripts/companies_ingest.py article <url>

Emits JSON array on stdout: [{name, linkedin_url?, description?}, ...]
For article mode, output is CANDIDATES — the skill does the final LLM
verification that each is a real company in this article's context.
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup


def ingest_csv(path: pathlib.Path) -> list[dict]:
    out: list[dict] = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("name") or "").strip()
            if not name:
                continue
            entry: dict = {"name": name}
            url = (row.get("url") or row.get("sameAs") or "").strip()
            if url:
                host = urlparse(url).hostname or ""
                if "linkedin.com" in host:
                    entry["linkedin_url"] = url
            desc = (row.get("description") or "").strip()
            if desc:
                entry["description"] = desc
            out.append(entry)
    return out


def extract_article_candidates(url: str, *, client: httpx.Client | None = None) -> list[dict]:
    """Fetch an article URL and return candidate company names with context snippets.

    Heuristic: collect the text of every <strong>, <b>, and <a> inside <article>
    or the body. Dedupe by name. Attach a ~200-char surrounding snippet for each.
    The skill does the LLM-verified filtering afterward — this pass is deliberately
    permissive.
    """
    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=20.0, follow_redirects=True)
    try:
        r = client.get(url)
        r.raise_for_status()
        html = r.text
    finally:
        if owns_client:
            client.close()

    soup = BeautifulSoup(html, "html.parser")
    root = soup.find("article") or soup.body or soup
    seen: dict[str, dict] = {}
    for el in root.find_all(["strong", "b", "a"]):
        name = el.get_text(strip=True)
        if not name or len(name) > 80 or "\n" in name:
            continue
        # Skip obvious non-names: lowercase-only, very short, digits-only
        if name.islower() or len(name) < 2 or name.isdigit():
            continue
        if name in seen:
            continue
        parent_text = el.parent.get_text(" ", strip=True) if el.parent else name
        snippet = parent_text[:200]
        seen[name] = {"name": name, "snippet": snippet}
    return list(seen.values())


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_csv = sub.add_parser("csv")
    p_csv.add_argument("path", type=pathlib.Path)

    p_art = sub.add_parser("article")
    p_art.add_argument("url")

    args = parser.parse_args(argv)
    if args.cmd == "csv":
        print(json.dumps(ingest_csv(args.path)))
        return 0
    if args.cmd == "article":
        print(json.dumps(extract_article_candidates(args.url)))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
