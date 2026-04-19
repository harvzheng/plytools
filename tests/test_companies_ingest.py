"""Tests for companies_ingest.py — CSV and article ingestion."""
from __future__ import annotations
import pathlib

from companies_ingest import ingest_csv

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def test_ingest_csv_returns_all_companies():
    companies = ingest_csv(FIXTURES / "soho_valley_sample.csv")
    names = [c["name"] for c in companies]
    assert names == ["Niva", "Daloopa", "Matter Bio", "Onlook", "Stepful"]


def test_ingest_csv_keeps_linkedin_urls():
    companies = ingest_csv(FIXTURES / "soho_valley_sample.csv")
    by_name = {c["name"]: c for c in companies}
    assert by_name["Niva"]["linkedin_url"] == "https://www.linkedin.com/company/withniva"
    assert by_name["Onlook"]["linkedin_url"] == "https://www.linkedin.com/company/onlook-dev/"


def test_ingest_csv_drops_non_linkedin_urls():
    companies = ingest_csv(FIXTURES / "soho_valley_sample.csv")
    by_name = {c["name"]: c for c in companies}
    # Matter Bio's URL is a google-maps link — should not populate linkedin_url
    assert by_name["Matter Bio"].get("linkedin_url") is None


def test_ingest_csv_handles_empty_url_field():
    companies = ingest_csv(FIXTURES / "soho_valley_sample.csv")
    by_name = {c["name"]: c for c in companies}
    assert by_name["Stepful"].get("linkedin_url") is None


def test_ingest_csv_includes_description():
    companies = ingest_csv(FIXTURES / "soho_valley_sample.csv")
    by_name = {c["name"]: c for c in companies}
    assert "AI" in by_name["Niva"]["description"]


import httpx
import respx

from companies_ingest import extract_article_candidates


@respx.mock
def test_extract_article_candidates_finds_links_and_strongs():
    html = (FIXTURES / "lux_article.html").read_text()
    respx.get("https://example.com/lux").mock(return_value=httpx.Response(200, text=html))
    candidates = extract_article_candidates("https://example.com/lux")
    names = [c["name"] for c in candidates]
    # Should find all the strong/link-based companies
    assert "Runway" in names
    assert "Hugging Face" in names
    assert "Anthropic" in names
    assert "Niva" in names
    assert "Heron Data" in names


@respx.mock
def test_extract_article_candidates_includes_context_snippet():
    html = (FIXTURES / "lux_article.html").read_text()
    respx.get("https://example.com/lux").mock(return_value=httpx.Response(200, text=html))
    candidates = extract_article_candidates("https://example.com/lux")
    by_name = {c["name"]: c for c in candidates}
    # Each candidate carries a surrounding snippet for LLM disambiguation
    assert "snippet" in by_name["Runway"]
    assert len(by_name["Runway"]["snippet"]) > 0


@respx.mock
def test_extract_article_candidates_dedupes_by_name():
    html = """
    <html><body>
      <p><strong>Alpha</strong> and <a href="#">Alpha</a> are great.</p>
    </body></html>
    """
    respx.get("https://example.com/dup").mock(return_value=httpx.Response(200, text=html))
    candidates = extract_article_candidates("https://example.com/dup")
    names = [c["name"] for c in candidates]
    assert names.count("Alpha") == 1
