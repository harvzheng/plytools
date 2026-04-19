#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "beautifulsoup4>=4.12"]
# ///
"""fetch_jobs.py — given a careers URL + ATS type, return role listings as JSON.

Usage:
  uv run scripts/fetch_jobs.py <careers-url> --ats <greenhouse|lever|ashby|generic>

Emits JSON array on stdout: [{title, location, url, snippet}, ...]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup


def _slug_from_careers_url(url: str) -> str:
    """Extract the board slug from a boards.greenhouse.io / jobs.lever.co / jobs.ashbyhq.com URL."""
    path = urlparse(url).path.strip("/")
    return path.split("/")[0] if path else ""


def _trim(text: str, n: int = 400) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:n]


def _strip_html(s: str) -> str:
    return BeautifulSoup(s or "", "html.parser").get_text(" ", strip=True)


def fetch_greenhouse(careers_url: str, *, client: httpx.Client | None = None) -> list[dict]:
    slug = _slug_from_careers_url(careers_url)
    api = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=20.0, follow_redirects=True)
    try:
        r = client.get(api, params={"content": "true"})
        r.raise_for_status()
        data = r.json()
    finally:
        if owns_client:
            client.close()
    out: list[dict] = []
    for j in data.get("jobs", []):
        out.append({
            "title": j.get("title") or "",
            "location": (j.get("location") or {}).get("name") or "",
            "url": j.get("absolute_url") or "",
            "snippet": _trim(_strip_html(j.get("content") or "")),
        })
    return out


def fetch_lever(careers_url: str, *, client: httpx.Client | None = None) -> list[dict]:
    slug = _slug_from_careers_url(careers_url)
    api = f"https://api.lever.co/v0/postings/{slug}"
    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=20.0, follow_redirects=True)
    try:
        r = client.get(api, params={"mode": "json"})
        r.raise_for_status()
        data = r.json()
    finally:
        if owns_client:
            client.close()
    out: list[dict] = []
    # Lever returns a flat list of postings.
    for p in data:
        categories = p.get("categories") or {}
        description_text = _strip_html(p.get("descriptionPlain") or p.get("description") or "")
        out.append({
            "title": p.get("text") or "",
            "location": categories.get("location") or "",
            "url": p.get("hostedUrl") or "",
            "snippet": _trim(description_text),
        })
    return out


def fetch_ashby(careers_url: str, *, client: httpx.Client | None = None) -> list[dict]:
    slug = _slug_from_careers_url(careers_url)
    api = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=20.0, follow_redirects=True)
    try:
        r = client.get(api, params={"includeCompensation": "false"})
        r.raise_for_status()
        data = r.json()
    finally:
        if owns_client:
            client.close()
    out: list[dict] = []
    for j in data.get("jobs", []):
        out.append({
            "title": j.get("title") or "",
            "location": j.get("locationName") or j.get("location") or "",
            "url": j.get("jobUrl") or j.get("applyUrl") or "",
            "snippet": _trim(_strip_html(j.get("descriptionHtml") or j.get("description") or "")),
        })
    return out


def fetch_generic(careers_url: str, *, client: httpx.Client | None = None) -> list[dict]:
    raise NotImplementedError  # Task 14


DISPATCH = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "generic": fetch_generic,
}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--ats", required=True, choices=list(DISPATCH.keys()))
    args = parser.parse_args(argv)
    try:
        jobs = DISPATCH[args.ats](args.url)
    except NotImplementedError:
        print(json.dumps({"error": f"ATS '{args.ats}' not yet implemented"}))
        return 1
    except httpx.HTTPError as e:
        print(json.dumps({"error": f"http: {e}"}))
        return 1
    print(json.dumps(jobs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
