"""Tests for resolve_careers.py — careers URL resolution with cache."""
from __future__ import annotations

import pathlib

from resolve_careers import CacheRow, read_cache, resolve, slug_for, write_cache_row


def test_slug_for_lowercases_and_strips_non_alnum():
    assert slug_for("Heron Data") == "herondata"
    assert slug_for("See|Me") == "seeme"
    assert slug_for("Matter Bio") == "matterbio"
    assert slug_for("TypingDNA") == "typingdna"


def test_read_cache_missing_returns_empty(tmp_path: pathlib.Path):
    assert read_cache(tmp_path / "cache.csv") == []


def test_write_cache_row_round_trip(tmp_path: pathlib.Path):
    path = tmp_path / "cache.csv"
    row = CacheRow(
        company="Niva",
        slug="niva",
        careers_url="https://jobs.ashbyhq.com/niva",
        ats="ashby",
        source="probe",
        resolved_at="2026-04-18",
    )
    write_cache_row(path, row)
    rows = read_cache(path)
    assert len(rows) == 1
    assert rows[0].company == "Niva"
    assert rows[0].ats == "ashby"


def test_resolve_returns_cache_hit(tmp_path: pathlib.Path):
    cache = tmp_path / "cache.csv"
    write_cache_row(cache, CacheRow(
        company="Niva", slug="niva",
        careers_url="https://jobs.ashbyhq.com/niva",
        ats="ashby", source="probe", resolved_at="2026-04-17",
    ))
    result = resolve("Niva", cache_path=cache)
    assert result["careers_url"] == "https://jobs.ashbyhq.com/niva"
    assert result["ats"] == "ashby"
    assert result["source"] == "probe"  # from cache


import httpx
import respx


@respx.mock
def test_resolve_probes_greenhouse_and_hits(tmp_path: pathlib.Path):
    # Probe hits the JSON API; cache stores the human-facing marketing URL.
    respx.get("https://boards-api.greenhouse.io/v1/boards/niva/jobs").mock(
        return_value=httpx.Response(200, json={"jobs": []})
    )
    result = resolve("Niva", cache_path=tmp_path / "cache.csv")
    assert result["careers_url"] == "https://boards.greenhouse.io/niva"
    assert result["ats"] == "greenhouse"
    assert result["source"] == "probe"
    rows = read_cache(tmp_path / "cache.csv")
    assert len(rows) == 1
    assert rows[0].careers_url == "https://boards.greenhouse.io/niva"


@respx.mock
def test_resolve_falls_through_to_ashby(tmp_path: pathlib.Path):
    respx.get("https://boards-api.greenhouse.io/v1/boards/daloopa/jobs").mock(
        return_value=httpx.Response(404)
    )
    respx.get("https://api.lever.co/v0/postings/daloopa").mock(
        return_value=httpx.Response(404)
    )
    respx.get("https://api.ashbyhq.com/posting-api/job-board/daloopa").mock(
        return_value=httpx.Response(200, json={"jobs": []})
    )
    result = resolve("Daloopa", cache_path=tmp_path / "cache.csv")
    assert result["careers_url"] == "https://jobs.ashbyhq.com/daloopa"
    assert result["ats"] == "ashby"


@respx.mock
def test_resolve_rejects_ashby_soft_404(tmp_path: pathlib.Path):
    # Regression: the old code probed jobs.ashbyhq.com/<slug> which returns 200 for
    # any slug (soft-404). The new code probes the API which correctly returns 404.
    respx.get("https://boards-api.greenhouse.io/v1/boards/obscure/jobs").mock(
        return_value=httpx.Response(404)
    )
    respx.get("https://api.lever.co/v0/postings/obscure").mock(
        return_value=httpx.Response(404)
    )
    respx.get("https://api.ashbyhq.com/posting-api/job-board/obscure").mock(
        return_value=httpx.Response(404)
    )
    result = resolve("Obscure", cache_path=tmp_path / "cache.csv")
    assert result["careers_url"] is None
    assert result["source"] == "needs_google_or_manual"
    # Cache NOT written yet on miss (skill does the follow-up)
    assert read_cache(tmp_path / "cache.csv") == []


def test_record_flag_writes_cache_row(tmp_path: pathlib.Path):
    # Simulates the skill calling --record after a successful WebSearch resolution.
    from resolve_careers import main
    cache = tmp_path / "cache.csv"
    rc = main([
        "--cache", str(cache), "--record",
        "Obscure Co", "https://obscure.co/careers", "generic", "google",
    ])
    assert rc == 0
    rows = read_cache(cache)
    assert len(rows) == 1
    assert rows[0].company == "Obscure Co"
    assert rows[0].careers_url == "https://obscure.co/careers"
    assert rows[0].source == "google"


def test_record_persists_across_cache_reads(tmp_path: pathlib.Path):
    from resolve_careers import main
    cache = tmp_path / "cache.csv"
    main(["--cache", str(cache), "--record", "X Co", "https://x.co/jobs", "generic", "manual"])
    # A second resolve() call should return the cached row without hitting probes.
    result = resolve("X Co", cache_path=cache)
    assert result["careers_url"] == "https://x.co/jobs"
    assert result["source"] == "manual"
