#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.27",
# ]
# ///
"""hunter_lookup.py — Hunter.io email-finder, domain-pattern, and account."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx

HUNTER_FIND = "https://api.hunter.io/v2/email-finder"
HUNTER_DOMAIN = "https://api.hunter.io/v2/domain-search"
HUNTER_ACCOUNT = "https://api.hunter.io/v2/account"


def _raise_on_quota(r: httpx.Response) -> None:
    if r.status_code == 401:
        raise RuntimeError("Hunter returned 401 — bad api_key")
    if r.status_code == 429:
        raise RuntimeError("Hunter returned 429 — quota exceeded")
    if r.status_code == 402:
        raise RuntimeError("Hunter returned 402 — payment required")
    r.raise_for_status()


def lookup_email(
    first: str,
    last: str,
    domain: str,
    api_key: str,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    owns = client is None
    client = client or httpx.Client(timeout=15.0)
    try:
        r = client.get(HUNTER_FIND, params={
            "domain": domain,
            "first_name": first,
            "last_name": last,
            "api_key": api_key,
        })
        _raise_on_quota(r)
        data = (r.json().get("data") or {})
        email = data.get("email")
        verification = (data.get("verification") or {}).get("status")
        confidence = verification or data.get("score") or None
        return {"email": email, "source": "hunter", "confidence": confidence}
    finally:
        if owns:
            client.close()


def find_pattern(domain: str, api_key: str, client: httpx.Client | None = None) -> str | None:
    owns = client is None
    client = client or httpx.Client(timeout=15.0)
    try:
        r = client.get(HUNTER_DOMAIN, params={"domain": domain, "api_key": api_key})
        _raise_on_quota(r)
        data = (r.json().get("data") or {})
        return data.get("pattern")
    finally:
        if owns:
            client.close()


def check_credits(api_key: str, client: httpx.Client | None = None) -> int:
    owns = client is None
    client = client or httpx.Client(timeout=10.0)
    try:
        r = client.get(HUNTER_ACCOUNT, params={"api_key": api_key})
        _raise_on_quota(r)
        data = r.json().get("data") or {}
        searches = (data.get("requests") or {}).get("searches") or {}
        return int(searches.get("available", 0))
    finally:
        if owns:
            client.close()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_lookup = sub.add_parser("lookup")
    p_lookup.add_argument("first")
    p_lookup.add_argument("last")
    p_lookup.add_argument("domain")
    p_pattern = sub.add_parser("pattern")
    p_pattern.add_argument("domain")
    sub.add_parser("credits")

    args = parser.parse_args(argv)
    api_key = os.environ.get("HUNTER_API_KEY")
    if not api_key:
        print(json.dumps({"error": "HUNTER_API_KEY not set"}))
        return 2
    try:
        if args.cmd == "lookup":
            result = lookup_email(args.first, args.last, args.domain, api_key=api_key)
        elif args.cmd == "pattern":
            result = {"pattern": find_pattern(args.domain, api_key=api_key), "source": "hunter"}
        elif args.cmd == "credits":
            result = {"credits_remaining": check_credits(api_key=api_key), "source": "hunter"}
    except RuntimeError as e:
        print(json.dumps({"error": str(e), "source": "hunter"}))
        return 3
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
