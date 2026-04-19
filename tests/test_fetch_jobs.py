"""Tests for fetch_jobs.py — per-ATS role fetchers."""
from __future__ import annotations
import json
import pathlib

import httpx
import respx

from fetch_jobs import fetch_greenhouse, fetch_lever, fetch_ashby, fetch_generic

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@respx.mock
def test_fetch_greenhouse_parses_job_board():
    payload = json.loads((FIXTURES / "greenhouse_board.json").read_text())
    respx.get("https://boards-api.greenhouse.io/v1/boards/airbnb/jobs").mock(
        return_value=httpx.Response(200, json=payload)
    )
    jobs = fetch_greenhouse("https://boards.greenhouse.io/airbnb")
    assert len(jobs) > 0
    # Every job dict has the four required keys
    for j in jobs:
        assert set(j.keys()) >= {"title", "location", "url", "snippet"}
        assert j["title"]  # non-empty


@respx.mock
def test_fetch_greenhouse_extracts_location():
    payload = json.loads((FIXTURES / "greenhouse_board.json").read_text())
    respx.get("https://boards-api.greenhouse.io/v1/boards/airbnb/jobs").mock(
        return_value=httpx.Response(200, json=payload)
    )
    jobs = fetch_greenhouse("https://boards.greenhouse.io/airbnb")
    # At least one job has a non-empty location string
    assert any(j["location"] for j in jobs)


@respx.mock
def test_fetch_greenhouse_snippet_is_truncated():
    payload = json.loads((FIXTURES / "greenhouse_board.json").read_text())
    respx.get("https://boards-api.greenhouse.io/v1/boards/airbnb/jobs").mock(
        return_value=httpx.Response(200, json=payload)
    )
    jobs = fetch_greenhouse("https://boards.greenhouse.io/airbnb")
    for j in jobs:
        assert len(j["snippet"]) <= 400


@respx.mock
def test_fetch_lever_parses_postings():
    payload = json.loads((FIXTURES / "lever_board.json").read_text())
    respx.get("https://api.lever.co/v0/postings/plaid").mock(
        return_value=httpx.Response(200, json=payload)
    )
    jobs = fetch_lever("https://jobs.lever.co/plaid")
    assert len(jobs) > 0
    for j in jobs:
        assert set(j.keys()) >= {"title", "location", "url", "snippet"}
        assert j["title"]


@respx.mock
def test_fetch_lever_snippet_is_truncated():
    payload = json.loads((FIXTURES / "lever_board.json").read_text())
    respx.get("https://api.lever.co/v0/postings/plaid").mock(
        return_value=httpx.Response(200, json=payload)
    )
    jobs = fetch_lever("https://jobs.lever.co/plaid")
    for j in jobs:
        assert len(j["snippet"]) <= 400


@respx.mock
def test_fetch_ashby_parses_job_board():
    payload = json.loads((FIXTURES / "ashby_board.json").read_text())
    respx.get("https://api.ashbyhq.com/posting-api/job-board/linear").mock(
        return_value=httpx.Response(200, json=payload)
    )
    jobs = fetch_ashby("https://jobs.ashbyhq.com/linear")
    assert len(jobs) > 0
    for j in jobs:
        assert set(j.keys()) >= {"title", "location", "url", "snippet"}
        assert j["title"]


@respx.mock
def test_fetch_ashby_snippet_is_truncated():
    payload = json.loads((FIXTURES / "ashby_board.json").read_text())
    respx.get("https://api.ashbyhq.com/posting-api/job-board/linear").mock(
        return_value=httpx.Response(200, json=payload)
    )
    jobs = fetch_ashby("https://jobs.ashbyhq.com/linear")
    for j in jobs:
        assert len(j["snippet"]) <= 400
