"""Tests for fetch_jd.py — JD HTML parsing + fetch."""
from __future__ import annotations
import pathlib

import httpx
import pytest
import respx

from fetch_jd import parse_jd, fetch_jd

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def test_parse_greenhouse():
    html = (FIXTURES / "jd_greenhouse.html").read_text()
    jd = parse_jd(html, source_url="https://boards.greenhouse.io/example/jobs/1")
    assert jd["title"] == "Product Designer"
    assert jd["company"] == "Example Corp"
    assert jd["location"] == "New York, NY"
    assert "compelling experiences" in jd["body"]
    assert jd["source"] == "greenhouse"


def test_parse_lever():
    html = (FIXTURES / "jd_lever.html").read_text()
    jd = parse_jd(html, source_url="https://jobs.lever.co/example/abc")
    assert jd["title"] == "Senior Engineer"
    assert jd["location"] == "Remote"
    assert jd["source"] == "lever"


def test_parse_ashby():
    html = (FIXTURES / "jd_ashby.html").read_text()
    jd = parse_jd(html, source_url="https://jobs.ashbyhq.com/acme/1")
    assert jd["title"] == "Designer"
    assert jd["location"] == "San Francisco"
    assert jd["source"] == "ashby"


@respx.mock
def test_fetch_jd_hits_url_and_parses():
    html = (FIXTURES / "jd_greenhouse.html").read_text()
    url = "https://boards.greenhouse.io/example/jobs/1"
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    jd = fetch_jd(url)
    assert jd["title"] == "Product Designer"
    assert jd["source_url"] == url


@respx.mock
def test_fetch_jd_raises_on_auth_wall():
    url = "https://www.linkedin.com/jobs/view/123"
    respx.get(url).mock(return_value=httpx.Response(401))
    with pytest.raises(RuntimeError, match="auth"):
        fetch_jd(url)
