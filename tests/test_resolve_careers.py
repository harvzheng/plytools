"""Tests for resolve_careers.py — careers URL resolution with cache."""
from __future__ import annotations
import pathlib

from resolve_careers import CacheRow, read_cache, write_cache_row, slug_for, resolve


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
    respx.head("https://boards.greenhouse.io/niva").mock(return_value=httpx.Response(200))
    result = resolve("Niva", cache_path=tmp_path / "cache.csv")
    assert result["careers_url"] == "https://boards.greenhouse.io/niva"
    assert result["ats"] == "greenhouse"
    assert result["source"] == "probe"
    # And the cache row should now be written
    rows = read_cache(tmp_path / "cache.csv")
    assert len(rows) == 1
    assert rows[0].careers_url == "https://boards.greenhouse.io/niva"


@respx.mock
def test_resolve_falls_through_to_ashby(tmp_path: pathlib.Path):
    respx.head("https://boards.greenhouse.io/daloopa").mock(return_value=httpx.Response(404))
    respx.head("https://job-boards.greenhouse.io/daloopa").mock(return_value=httpx.Response(404))
    respx.head("https://jobs.lever.co/daloopa").mock(return_value=httpx.Response(404))
    respx.head("https://jobs.ashbyhq.com/daloopa").mock(return_value=httpx.Response(200))
    result = resolve("Daloopa", cache_path=tmp_path / "cache.csv")
    assert result["careers_url"] == "https://jobs.ashbyhq.com/daloopa"
    assert result["ats"] == "ashby"


@respx.mock
def test_resolve_all_miss_returns_needs_google(tmp_path: pathlib.Path):
    for _, tpl in [
        ("greenhouse", "https://boards.greenhouse.io/{slug}"),
        ("greenhouse", "https://job-boards.greenhouse.io/{slug}"),
        ("lever", "https://jobs.lever.co/{slug}"),
        ("ashby", "https://jobs.ashbyhq.com/{slug}"),
    ]:
        respx.head(tpl.format(slug="obscure")).mock(return_value=httpx.Response(404))
    result = resolve("Obscure", cache_path=tmp_path / "cache.csv")
    assert result["careers_url"] is None
    assert result["source"] == "needs_google_or_manual"
    # Cache NOT written yet on miss (skill does the follow-up)
    assert read_cache(tmp_path / "cache.csv") == []
