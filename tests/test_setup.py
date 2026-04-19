"""Tests for setup.py — .env reader/writer + validation shim."""
from __future__ import annotations

import pathlib

import httpx
import respx
from setup import (
    PROVIDERS,
    _mask,
    load_env,
    render_env,
    save_env,
    validate,
)


def test_load_env_missing_file_returns_empty(tmp_path: pathlib.Path):
    assert load_env(tmp_path / "nope.env") == {}


def test_load_env_parses_comments_and_blanks(tmp_path: pathlib.Path):
    path = tmp_path / ".env"
    path.write_text("""
# Apollo
APOLLO_API_KEY=abc123

# Hunter
HUNTER_API_KEY=xyz789
""")
    env = load_env(path)
    assert env == {"APOLLO_API_KEY": "abc123", "HUNTER_API_KEY": "xyz789"}


def test_render_env_stable_order_and_comments():
    out = render_env({"APOLLO_API_KEY": "a", "HUNTER_API_KEY": "h"})
    # APOLLO section appears before HUNTER per PROVIDERS order
    assert out.index("APOLLO_API_KEY=a") < out.index("HUNTER_API_KEY=h")
    assert "Apollo.io" in out
    assert "Hunter.io" in out


def test_render_env_missing_key_renders_blank():
    out = render_env({"APOLLO_API_KEY": "only-apollo"})
    assert "APOLLO_API_KEY=only-apollo" in out
    assert "HUNTER_API_KEY=" in out


def test_save_and_load_roundtrip(tmp_path: pathlib.Path):
    path = tmp_path / ".env"
    save_env({"APOLLO_API_KEY": "k1", "HUNTER_API_KEY": "k2"}, path=path)
    assert load_env(path) == {"APOLLO_API_KEY": "k1", "HUNTER_API_KEY": "k2"}


def test_mask_short_key():
    assert _mask("abcd") == "••••"


def test_mask_long_key():
    assert _mask("sk_abcdefghij") == "••••ghij"


def test_mask_empty():
    assert _mask("") == ""


def test_validate_skips_empty_key():
    ok, msg = validate("APOLLO_API_KEY", "")
    assert ok is False
    assert "skipped" in msg.lower()


@respx.mock
def test_validate_apollo_success():
    respx.get("https://api.apollo.io/api/v1/auth/health").mock(
        return_value=httpx.Response(200, json={"credits_used": 5, "credits_limit": 50})
    )
    ok, msg = validate("APOLLO_API_KEY", "k")
    assert ok is True
    assert "45" in msg


@respx.mock
def test_validate_apollo_failure():
    respx.get("https://api.apollo.io/api/v1/auth/health").mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"})
    )
    ok, msg = validate("APOLLO_API_KEY", "bad")
    assert ok is False
    assert "failed" in msg.lower()


@respx.mock
def test_validate_hunter_success():
    respx.get("https://api.hunter.io/v2/account").mock(
        return_value=httpx.Response(200, json={"data": {"requests": {"searches": {"available": 25, "used": 0}}}})
    )
    ok, msg = validate("HUNTER_API_KEY", "k")
    assert ok is True
    assert "25" in msg


def test_providers_cover_both_keys():
    names = {p[0] for p in PROVIDERS}
    assert names == {"APOLLO_API_KEY", "HUNTER_API_KEY"}
