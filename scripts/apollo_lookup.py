#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.27",
# ]
# ///
"""apollo_lookup.py — look up an email on Apollo.io and check credits."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx

APOLLO_MATCH_URL = "https://api.apollo.io/api/v1/people/match"
APOLLO_HEALTH_URL = "https://api.apollo.io/api/v1/auth/health"


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
        r = client.post(
            APOLLO_MATCH_URL,
            json={
                "api_key": api_key,
                "first_name": first,
                "last_name": last,
                "domain": domain,
                "reveal_personal_emails": False,
            },
        )
        if r.status_code == 402:
            raise RuntimeError("Apollo returned 402 — out of credits")
        if r.status_code == 429:
            raise RuntimeError("Apollo returned 429 — rate limited")
        if r.status_code == 401:
            raise RuntimeError("Apollo returned 401 — bad api_key")
        r.raise_for_status()
        data = r.json()
        person = data.get("person") or {}
        email = person.get("email")
        status = person.get("email_status")
        return {
            "email": email,
            "source": "apollo",
            "confidence": status or ("unknown" if email else None),
        }
    finally:
        if owns:
            client.close()


def check_credits(api_key: str, client: httpx.Client | None = None) -> int:
    """Return estimated credits remaining. Raises on auth/network errors."""
    owns = client is None
    client = client or httpx.Client(timeout=10.0)
    try:
        r = client.get(APOLLO_HEALTH_URL, params={"api_key": api_key})
        r.raise_for_status()
        data = r.json()
        used = int(data.get("credits_used", 0))
        limit = int(data.get("credits_limit", 0))
        return max(limit - used, 0)
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
    sub.add_parser("credits")

    args = parser.parse_args(argv)
    api_key = os.environ.get("APOLLO_API_KEY")
    if not api_key:
        print(json.dumps({"error": "APOLLO_API_KEY not set"}))
        return 2
    try:
        if args.cmd == "lookup":
            result = lookup_email(args.first, args.last, args.domain, api_key=api_key)
        elif args.cmd == "credits":
            result = {"credits_remaining": check_credits(api_key=api_key), "source": "apollo"}
    except RuntimeError as e:
        print(json.dumps({"error": str(e), "source": "apollo"}))
        return 3
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
