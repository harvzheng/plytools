"""Tests for hunter_lookup.py."""
from __future__ import annotations
import httpx
import respx

from hunter_lookup import check_credits, find_pattern, lookup_email


HUNTER_FIND = "https://api.hunter.io/v2/email-finder"
HUNTER_DOMAIN = "https://api.hunter.io/v2/domain-search"
HUNTER_ACCOUNT = "https://api.hunter.io/v2/account"


@respx.mock
def test_lookup_email_found():
    respx.get(HUNTER_FIND).mock(return_value=httpx.Response(200, json={
        "data": {"email": "alex@example.com", "score": 94, "verification": {"status": "valid"}}
    }))
    result = lookup_email("Alex", "Chen", "example.com", api_key="k")
    assert result["email"] == "alex@example.com"
    assert result["source"] == "hunter"
    assert result["confidence"] in ("valid", 94, "94")


@respx.mock
def test_lookup_email_not_found():
    respx.get(HUNTER_FIND).mock(return_value=httpx.Response(200, json={"data": {"email": None, "score": 0}}))
    result = lookup_email("No", "One", "example.com", api_key="k")
    assert result["email"] is None


@respx.mock
def test_lookup_email_quota_exceeded():
    respx.get(HUNTER_FIND).mock(return_value=httpx.Response(429, json={"errors": [{"details": "Usage exceeded"}]}))
    try:
        lookup_email("X", "Y", "example.com", api_key="k")
    except RuntimeError as e:
        assert "429" in str(e) or "rate" in str(e).lower() or "quota" in str(e).lower()
    else:
        raise AssertionError("expected RuntimeError")


@respx.mock
def test_find_pattern_returns_dominant():
    respx.get(HUNTER_DOMAIN).mock(return_value=httpx.Response(200, json={
        "data": {"pattern": "{first}", "organization": "Example Corp"}
    }))
    pattern = find_pattern("example.com", api_key="k")
    assert pattern == "{first}"


@respx.mock
def test_check_credits_uses_account_endpoint():
    respx.get(HUNTER_ACCOUNT).mock(return_value=httpx.Response(200, json={
        "data": {"requests": {"searches": {"available": 23, "used": 2}}}
    }))
    remaining = check_credits(api_key="k")
    assert remaining == 23
