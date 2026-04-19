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
