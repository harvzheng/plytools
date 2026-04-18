"""Tests for apollo_lookup.py."""
from __future__ import annotations
import httpx
import respx

from apollo_lookup import check_credits, lookup_email


APOLLO_MATCH_URL = "https://api.apollo.io/api/v1/people/match"
APOLLO_HEALTH_URL = "https://api.apollo.io/api/v1/auth/health"


@respx.mock
def test_lookup_email_found():
    respx.post(APOLLO_MATCH_URL).mock(
        return_value=httpx.Response(200, json={
            "person": {"email": "alex@example.com", "email_status": "verified"},
        })
    )
    result = lookup_email("Alex", "Chen", "example.com", api_key="k")
    assert result["email"] == "alex@example.com"
    assert result["source"] == "apollo"
    assert result["confidence"] == "verified"


@respx.mock
def test_lookup_email_not_found_returns_null():
    respx.post(APOLLO_MATCH_URL).mock(return_value=httpx.Response(200, json={"person": None}))
    result = lookup_email("No", "One", "example.com", api_key="k")
    assert result["email"] is None
    assert result["source"] == "apollo"


@respx.mock
def test_lookup_email_out_of_credits_raises():
    respx.post(APOLLO_MATCH_URL).mock(return_value=httpx.Response(402, json={"error": "insufficient credits"}))
    try:
        lookup_email("X", "Y", "example.com", api_key="k")
    except RuntimeError as e:
        assert "credits" in str(e).lower()
    else:
        raise AssertionError("expected RuntimeError")


@respx.mock
def test_check_credits_returns_remaining():
    respx.get(APOLLO_HEALTH_URL).mock(return_value=httpx.Response(200, json={
        "is_logged_in": True,
        "credits_used": 3,
        "credits_limit": 50,
    }))
    remaining = check_credits(api_key="k")
    assert remaining == 47
