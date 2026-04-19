"""Tests for shortlist.py — per-run role shortlist read/append/status."""
from __future__ import annotations

import pathlib

from shortlist import Row, append_row, read_shortlist, render_shortlist, set_status


def test_read_shortlist_missing_file_returns_empty(tmp_path: pathlib.Path):
    assert read_shortlist(tmp_path / "shortlist.md") == []


def test_append_row_creates_file_with_header(tmp_path: pathlib.Path):
    path = tmp_path / "shortlist.md"
    row = Row(
        company="Niva",
        role="Design Engineer",
        location="NYC",
        url="https://jobs.ashbyhq.com/niva/abc",
        reason="Design-engineer hybrid role, aligns with portfolio",
        status="pending",
    )
    append_row(path, row)
    content = path.read_text()
    assert "| Company |" in content
    assert "Niva" in content
    assert "Design Engineer" in content
    assert "pending" in content


def test_append_row_preserves_existing_rows(tmp_path: pathlib.Path):
    path = tmp_path / "shortlist.md"
    r1 = Row("A", "Designer", "NYC", "https://a", "fit", "pending")
    r2 = Row("B", "Design Eng", "Remote", "https://b", "maybe", "pending")
    append_row(path, r1)
    append_row(path, r2)
    rows = read_shortlist(path)
    assert len(rows) == 2
    assert rows[0].company == "A"
    assert rows[1].company == "B"


def test_render_shortlist_formats_table():
    rows = [
        Row("A", "Designer", "NYC", "https://a", "fit", "pending"),
        Row("B", "Design Eng", "Remote", "https://b", "maybe", "approved"),
    ]
    out = render_shortlist(rows)
    lines = out.strip().splitlines()
    assert len(lines) == 4  # header + separator + 2 rows
    assert lines[0].startswith("| Company")
    assert "approved" in lines[3]


def test_set_status_updates_existing_row(tmp_path: pathlib.Path):
    path = tmp_path / "shortlist.md"
    append_row(path, Row("A", "Designer", "NYC", "https://a", "fit", "pending"))
    append_row(path, Row("B", "Design Eng", "Remote", "https://b", "maybe", "pending"))
    set_status(path, 1, "approved")
    rows = read_shortlist(path)
    assert rows[0].status == "pending"
    assert rows[1].status == "approved"


def test_set_status_rejects_invalid_status(tmp_path: pathlib.Path):
    path = tmp_path / "shortlist.md"
    append_row(path, Row("A", "Designer", "NYC", "https://a", "fit", "pending"))
    import pytest
    with pytest.raises(ValueError):
        set_status(path, 0, "bogus")


def test_set_status_rejects_out_of_range(tmp_path: pathlib.Path):
    path = tmp_path / "shortlist.md"
    append_row(path, Row("A", "Designer", "NYC", "https://a", "fit", "pending"))
    import pytest
    with pytest.raises(IndexError):
        set_status(path, 5, "approved")
