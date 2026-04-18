#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.27",
#     "beautifulsoup4>=4.12",
# ]
# ///
"""fetch_jd.py — fetch a JD URL and parse into structured data.

Supported shapes: Greenhouse, Lever, Ashby, and a generic fallback.
LinkedIn, Workday, and other auth-walled sources are NOT supported — the
caller should prompt the user to paste the JD instead.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from typing import Any

import httpx
from bs4 import BeautifulSoup


def _detect_source(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    if "greenhouse" in host:
        return "greenhouse"
    if "lever" in host:
        return "lever"
    if "ashby" in host:
        return "ashby"
    if "linkedin" in host:
        return "linkedin"
    return "generic"


def _text(el) -> str:
    return el.get_text(strip=True) if el else ""


def parse_jd(html: str, source_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    source = _detect_source(source_url)

    if source == "greenhouse":
        title = _text(soup.select_one(".app-title, h1"))
        company = _text(soup.select_one(".company-name"))
        location = _text(soup.select_one(".location"))
        body = _text(soup.select_one("#content"))
    elif source == "lever":
        title = _text(soup.select_one(".posting-headline h2, .posting-headline h1"))
        company = ""
        location = _text(soup.select_one(".posting-categories .location, .location"))
        body = _text(soup.select_one(".section-wrapper"))
    elif source == "ashby":
        title = _text(soup.select_one(".job-posting h1, h1"))
        company = ""
        location = _text(soup.select_one(".location-name, .location"))
        body = _text(soup.select_one(".job-description"))
    else:
        title = _text(soup.select_one("h1"))
        company = ""
        location = ""
        body = _text(soup.select_one("main")) or _text(soup.select_one("body"))

    title_tag = soup.find("title")
    if title_tag and not company:
        # "Role at Company" / "Role — Company"
        text = title_tag.get_text(strip=True)
        for sep in [" at ", " — ", " - ", " | "]:
            if sep in text:
                parts = text.split(sep, 1)
                if not title:
                    title = parts[0].strip()
                company = parts[1].strip()
                break

    return {
        "title": title,
        "company": company,
        "location": location,
        "body": body,
        "source": source,
        "source_url": source_url,
    }


def fetch_jd(url: str, client: httpx.Client | None = None) -> dict[str, Any]:
    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=15.0, headers={"User-Agent": "plytools/0.1"})
    try:
        r = client.get(url)
        if r.status_code in (401, 403):
            raise RuntimeError(f"auth wall fetching {url} (HTTP {r.status_code}) — ask user to paste the JD text instead.")
        r.raise_for_status()
        return parse_jd(r.text, source_url=url)
    finally:
        if owns_client:
            client.close()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    args = parser.parse_args(argv)
    try:
        jd = fetch_jd(args.url)
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}))
        return 2
    print(json.dumps(jd, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
