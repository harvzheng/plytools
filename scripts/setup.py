#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.27",
# ]
# ///
"""setup.py — interactive `.env` configuration for Apollo and Hunter API keys.

Run once after cloning:
    uv run scripts/setup.py

Prompts for each key (press Enter to skip either), writes them to `.env` at
the repo root, and optionally validates each key by hitting the provider's
usage endpoint (free, no credits burned).
"""
from __future__ import annotations

import getpass
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"

PROVIDERS = [
    ("APOLLO_API_KEY", "Apollo.io", "https://www.apollo.io/pricing (API requires a paid plan)"),
    ("HUNTER_API_KEY", "Hunter.io", "https://hunter.io/api (free tier includes API access)"),
]


def load_env(path: pathlib.Path = ENV_PATH) -> dict[str, str]:
    """Parse a .env file into a dict. Empty dict if file missing."""
    if not path.exists():
        return {}
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            k, _, v = stripped.partition("=")
            env[k.strip()] = v.strip()
    return env


def render_env(env: dict[str, str]) -> str:
    """Render a .env file contents from a dict. Stable ordering by PROVIDERS."""
    lines: list[str] = []
    for key, name, url in PROVIDERS:
        lines.append(f"# {name} — {url}")
        lines.append(f"{key}={env.get(key, '')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def save_env(env: dict[str, str], path: pathlib.Path = ENV_PATH) -> None:
    path.write_text(render_env(env))


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "•" * len(key)
    return "••••" + key[-4:]


def prompt_key(name: str, existing: str, url_hint: str) -> str:
    """Prompt for a single key. Returns the new value (may equal existing)."""
    if existing:
        print(f"  {name} is already set ({_mask(existing)}).")
        answer = input("  Replace? [y/N]: ").strip().lower()
        if answer != "y":
            return existing
    print(f"  Get a key at: {url_hint}")
    new = getpass.getpass(f"  Paste {name} (or press Enter to skip): ").strip()
    return new or existing


def validate(key_name: str, api_key: str) -> tuple[bool, str]:
    """Call the provider's credits endpoint. Returns (ok, message)."""
    if not api_key:
        return False, "(skipped — no key)"
    # Deferred imports so the module loads fine even without deps on a
    # setup-only run that skips both providers.
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    try:
        if key_name == "APOLLO_API_KEY":
            from apollo_lookup import check_credits
            remaining = check_credits(api_key=api_key)
            return True, f"OK — {remaining} credits remaining"
        if key_name == "HUNTER_API_KEY":
            from hunter_lookup import check_credits
            remaining = check_credits(api_key=api_key)
            return True, f"OK — {remaining} searches remaining"
    except Exception as e:  # network, auth, parsing — surface verbatim
        return False, f"validation failed: {e}"
    return False, "unknown provider"


def main() -> int:
    print("plytools setup — configure API keys for Apollo and Hunter.")
    print(f"Keys are saved to {ENV_PATH} (gitignored). Press Enter to skip either.\n")

    env = load_env()

    for key_name, name, url in PROVIDERS:
        print(f"─── {name} ───")
        env[key_name] = prompt_key(key_name, env.get(key_name, ""), url)
        print()

    save_env(env)
    print(f"Saved → {ENV_PATH}")

    # Validation pass
    any_key = any(env.get(k) for k, *_ in PROVIDERS)
    if not any_key:
        print("\nNo keys configured. The skill will fall through to manual lookup.")
        return 0

    print("\nValidating keys (free; does not consume credits)…")
    for key_name, name, _ in PROVIDERS:
        api_key = env.get(key_name, "")
        ok, msg = validate(key_name, api_key)
        marker = "✓" if ok else ("·" if not api_key else "✗")
        print(f"  {marker} {name}: {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
