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
