"""Tests for pipeline.py — application index read/append."""
from __future__ import annotations
import pathlib
import pytest

from pipeline import Row, append_row, read_index, render_index


def test_read_index_missing_file_returns_empty(tmp_path: pathlib.Path):
    assert read_index(tmp_path / "index.md") == []


def test_append_row_creates_file_with_header(tmp_path: pathlib.Path):
    path = tmp_path / "index.md"
    row = Row(
        company="Example Corp",
        role="Product Designer",
        stage="Warm-intro requested",
        last_action="Emailed Jamie",
        next_step="Wait 3 days",
        updated="2026-04-18",
    )
    append_row(path, row)
    content = path.read_text()
    assert "| Company |" in content
    assert "Example Corp" in content
    assert "Product Designer" in content


def test_append_row_preserves_existing_rows(tmp_path: pathlib.Path):
    path = tmp_path / "index.md"
    r1 = Row("A", "Designer", "Draft", "None", "Send", "2026-04-17")
    r2 = Row("B", "Engineer", "Sent", "Emailed CTO", "Follow up", "2026-04-18")
    append_row(path, r1)
    append_row(path, r2)
    rows = read_index(path)
    assert len(rows) == 2
    assert rows[0].company == "A"
    assert rows[1].company == "B"


def test_render_index_formats_table(tmp_path: pathlib.Path):
    rows = [
        Row("A", "Designer", "Draft", "None", "Send", "2026-04-17"),
        Row("B", "Engineer", "Sent", "Emailed CTO", "Follow up", "2026-04-18"),
    ]
    out = render_index(rows)
    lines = out.strip().splitlines()
    # header + separator + 2 rows
    assert len(lines) == 4
    assert lines[0].startswith("| Company")
