#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# ///
"""email_fallback.py — apply a Hunter-style pattern to a name + domain."""
from __future__ import annotations

import argparse
import json
import re
import sys

_VALID_TOKENS = {"first", "last", "f", "l"}


def apply_pattern(first: str, last: str, domain: str, pattern: str) -> str:
    first = first.strip().lower()
    last = last.strip().lower()
    domain = domain.strip().lower()

    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if token == "first":
            return first
        if token == "last":
            return last
        if token == "f":
            return first[:1]
        if token == "l":
            return last[:1]
        raise ValueError(f"unknown token in pattern: {{{token}}}")

    local = re.sub(r"\{([a-z]+)\}", replace, pattern)
    return f"{local}@{domain}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("first")
    parser.add_argument("last")
    parser.add_argument("domain")
    parser.add_argument("pattern")
    args = parser.parse_args(argv)
    try:
        email = apply_pattern(args.first, args.last, args.domain, args.pattern)
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        return 2
    print(json.dumps({"email": email, "source": "pattern", "confidence": "guessed"}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
