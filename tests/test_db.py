"""Tests for db.py — applications SQLite read/write."""
from __future__ import annotations

import pathlib
import sqlite3

import pytest

from db import (
    dedupe_role_slugs,
    import_shortlist,
    list_rows,
    open_db,
    read_shortlist,
    reconcile,
    render_table,
    slugify,
    upsert,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_db(tmp_path: pathlib.Path) -> sqlite3.Connection:
    """Create a fresh test DB with the applications schema.

    Uses sqlite3.connect directly (not open_db) so the file-existence guard
    in open_db doesn't interfere with test setup.
    """
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS applications (
            id            INTEGER PRIMARY KEY,
            company_slug  TEXT NOT NULL,
            role_slug     TEXT NOT NULL,
            company       TEXT NOT NULL,
            role          TEXT NOT NULL,
            stage         TEXT NOT NULL DEFAULT 'Discovered',
            priority      INTEGER,
            last_action   TEXT,
            next_step     TEXT,
            notes         TEXT,
            updated       TEXT NOT NULL,
            created_at    TEXT NOT NULL,
            UNIQUE (company_slug, role_slug)
        );
        """
    )
    return conn


def make_shortlist(path: pathlib.Path, rows: list[tuple]) -> None:
    """Write a shortlist markdown table to path."""
    lines = [
        "| Company | Role | Location | URL | Reason | Status |",
        "|---|---|---|---|---|---|",
    ]
    for co, role, loc, url, reason, status in rows:
        lines.append(f"| {co} | {role} | {loc} | {url} | {reason} | {status} |")
    path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------


def test_slugify_basic():
    assert slugify("Example Corp") == "example-corp"


def test_slugify_ampersand():
    assert slugify("Weights & Biases") == "weights-and-biases"


def test_slugify_strips_punctuation():
    assert slugify("Foo, Inc.") == "foo-inc"


def test_slugify_strips_leading_trailing_hyphens():
    assert slugify("--hello--") == "hello"


# ---------------------------------------------------------------------------
# upsert — insert
# ---------------------------------------------------------------------------


def test_upsert_creates_row_when_new(tmp_path):
    conn = make_db(tmp_path)
    upsert(conn, "Example Corp", "Product Designer", "Discovered", "JD ingested", "Pull contacts", "2026-04-19")
    rows = list_rows(conn)
    assert len(rows) == 1
    assert rows[0]["company"] == "Example Corp"
    assert rows[0]["stage"] == "Discovered"


def test_upsert_sets_created_at_on_insert(tmp_path):
    conn = make_db(tmp_path)
    upsert(conn, "Acme", "Designer", "Discovered", "-", "-", "2026-04-19")
    row = conn.execute("SELECT created_at FROM applications").fetchone()
    assert row["created_at"]  # non-empty ISO date


# ---------------------------------------------------------------------------
# upsert — update
# ---------------------------------------------------------------------------


def test_upsert_updates_existing_row(tmp_path):
    conn = make_db(tmp_path)
    upsert(conn, "OpenRouter", "Product Designer", "Discovered", "JD ingested", "Pull contacts", "2026-04-19")
    upsert(conn, "OpenRouter", "Product Designer", "Drafts ready", "V2 picked", "Send V2", "2026-04-20")
    rows = list_rows(conn)
    assert len(rows) == 1
    assert rows[0]["stage"] == "Drafts ready"
    assert rows[0]["last_action"] == "V2 picked"


def test_upsert_preserves_created_at_on_re_upsert(tmp_path):
    conn = make_db(tmp_path)
    upsert(conn, "OpenRouter", "Product Designer", "Discovered", "-", "-", "2026-04-19")
    original_created = conn.execute("SELECT created_at FROM applications").fetchone()["created_at"]
    upsert(conn, "OpenRouter", "Product Designer", "Applied", "sent", "wait", "2026-04-21")
    after_created = conn.execute("SELECT created_at FROM applications").fetchone()["created_at"]
    assert original_created == after_created


def test_upsert_distinguishes_different_roles_at_same_company(tmp_path):
    conn = make_db(tmp_path)
    upsert(conn, "Foo", "Designer", "Discovered", "-", "-", "2026-04-19")
    upsert(conn, "Foo", "Engineer", "Discovered", "-", "-", "2026-04-19")
    assert len(list_rows(conn)) == 2


# ---------------------------------------------------------------------------
# append — synonym for upsert
# ---------------------------------------------------------------------------


def test_append_inserts_when_row_does_not_exist(tmp_path):
    conn = make_db(tmp_path)
    upsert(conn, "NewCo", "Designer", "Discovered", "-", "-", "2026-04-19")
    rows = list_rows(conn)
    assert rows[0]["company"] == "NewCo"


def test_append_updates_when_row_exists(tmp_path):
    """append is an alias of upsert — it overwrites an existing row."""
    conn = make_db(tmp_path)
    upsert(conn, "NewCo", "Designer", "Discovered", "shortlisted", "ingest", "2026-04-19")
    upsert(conn, "NewCo", "Designer", "Applied", "sent", "wait", "2026-04-21")
    rows = list_rows(conn)
    assert len(rows) == 1
    assert rows[0]["stage"] == "Applied"


# ---------------------------------------------------------------------------
# priority
# ---------------------------------------------------------------------------


def test_priority_set_on_upsert(tmp_path):
    conn = make_db(tmp_path)
    upsert(conn, "Acme", "Designer", "Discovered", "-", "-", "2026-04-19", priority=3)
    row = conn.execute("SELECT priority FROM applications").fetchone()
    assert row["priority"] == 3


def test_clear_priority_nulls_it(tmp_path):
    conn = make_db(tmp_path)
    upsert(conn, "Acme", "Designer", "Discovered", "-", "-", "2026-04-19", priority=3)
    upsert(conn, "Acme", "Designer", "Discovered", "-", "-", "2026-04-19", clear_priority=True)
    row = conn.execute("SELECT priority FROM applications").fetchone()
    assert row["priority"] is None


def test_priority_preserved_when_not_passed(tmp_path):
    conn = make_db(tmp_path)
    upsert(conn, "Acme", "Designer", "Discovered", "-", "-", "2026-04-19", priority=5)
    upsert(conn, "Acme", "Designer", "Applied", "sent", "wait", "2026-04-21")
    row = conn.execute("SELECT priority FROM applications").fetchone()
    assert row["priority"] == 5


# ---------------------------------------------------------------------------
# --db override
# ---------------------------------------------------------------------------


def test_db_path_override(tmp_path):
    """Data written to a custom DB path is readable from that path only."""
    import subprocess, sys

    custom_db_path = tmp_path / "custom.db"
    # Bootstrap the schema in the custom DB
    conn = sqlite3.connect(custom_db_path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS applications (
            id            INTEGER PRIMARY KEY,
            company_slug  TEXT NOT NULL,
            role_slug     TEXT NOT NULL,
            company       TEXT NOT NULL,
            role          TEXT NOT NULL,
            stage         TEXT NOT NULL DEFAULT 'Discovered',
            priority      INTEGER,
            last_action   TEXT,
            next_step     TEXT,
            notes         TEXT,
            updated       TEXT NOT NULL,
            created_at    TEXT NOT NULL,
            UNIQUE (company_slug, role_slug)
        );
        """
    )
    conn.close()

    scripts_db = pathlib.Path(__file__).parent.parent / "scripts" / "db.py"
    result = subprocess.run(
        [sys.executable, str(scripts_db), "--db", str(custom_db_path),
         "upsert", "TestCo", "Designer", "Discovered", "-", "-", "2026-04-19"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    # Verify the row appears in the custom DB, not some default location
    conn2 = sqlite3.connect(custom_db_path)
    conn2.row_factory = sqlite3.Row
    rows = conn2.execute("SELECT company FROM applications").fetchall()
    assert len(rows) == 1
    assert rows[0]["company"] == "TestCo"


# ---------------------------------------------------------------------------
# list — sort order
# ---------------------------------------------------------------------------


def test_list_produces_pipe_table_with_correct_headers(tmp_path):
    conn = make_db(tmp_path)
    upsert(conn, "Alpha", "Designer", "Discovered", "-", "-", "2026-04-19")
    output = render_table(list_rows(conn))
    lines = output.strip().splitlines()
    assert lines[0].startswith("| Company")
    assert "Role" in lines[0]
    assert "Stage" in lines[0]
    assert "Last action" in lines[0]
    assert "Next" in lines[0]
    assert "Updated" in lines[0]
    # header + separator + 1 data row
    assert len(lines) == 3


def test_list_sort_order_updated_desc_then_company(tmp_path):
    conn = make_db(tmp_path)
    upsert(conn, "Zebra Corp", "Designer", "Discovered", "-", "-", "2026-04-17")
    upsert(conn, "Alpha Inc", "Engineer", "Discovered", "-", "-", "2026-04-19")
    upsert(conn, "Beta Co", "PM", "Discovered", "-", "-", "2026-04-18")
    rows = list_rows(conn)
    # Most recent updated first
    assert rows[0]["company"] == "Alpha Inc"
    assert rows[1]["company"] == "Beta Co"
    assert rows[2]["company"] == "Zebra Corp"


def test_list_sort_order_ties_broken_by_company(tmp_path):
    conn = make_db(tmp_path)
    upsert(conn, "Zebra", "Designer", "Discovered", "-", "-", "2026-04-19")
    upsert(conn, "Alpha", "Designer", "Discovered", "-", "-", "2026-04-19")
    rows = list_rows(conn)
    assert rows[0]["company"] == "Alpha"
    assert rows[1]["company"] == "Zebra"


# ---------------------------------------------------------------------------
# reconcile
# ---------------------------------------------------------------------------


def test_reconcile_creates_folder_only_row_for_orphan_folder(tmp_path):
    conn = make_db(tmp_path)
    apps = tmp_path / "applications"
    (apps / "stainless" / "product-designer").mkdir(parents=True)
    reconcile(conn, apps)
    rows = list_rows(conn)
    assert len(rows) == 1
    assert rows[0]["stage"] == "Folder only"
    assert rows[0]["next_step"] == "Add to index"


def test_reconcile_leaves_existing_rows_untouched(tmp_path):
    conn = make_db(tmp_path)
    apps = tmp_path / "applications"
    (apps / "stainless" / "product-designer").mkdir(parents=True)
    # Pre-seed a row for this folder
    upsert(conn, "Stainless", "Product Designer", "Applied", "sent", "wait", "2026-04-20")
    reconcile(conn, apps)
    rows = list_rows(conn)
    assert len(rows) == 1
    assert rows[0]["stage"] == "Applied"  # not overwritten


def test_reconcile_skips_underscore_prefixed_dirs(tmp_path):
    conn = make_db(tmp_path)
    apps = tmp_path / "applications"
    (apps / "_triage").mkdir(parents=True)
    (apps / "_triage" / "some-role").mkdir()
    reconcile(conn, apps)
    assert list_rows(conn) == []


def test_reconcile_is_idempotent(tmp_path):
    conn = make_db(tmp_path)
    apps = tmp_path / "applications"
    (apps / "wandb" / "senior-product-designer").mkdir(parents=True)
    reconcile(conn, apps)
    first = list_rows(conn)
    reconcile(conn, apps)
    second = list_rows(conn)
    assert first == second


def test_reconcile_derives_company_from_slug(tmp_path):
    """Orphan folder slugs are title-cased into human-readable company/role names."""
    conn = make_db(tmp_path)
    apps = tmp_path / "applications"
    (apps / "wandb" / "founding-designer").mkdir(parents=True)
    reconcile(conn, apps)
    rows = list_rows(conn)
    assert len(rows) == 1
    assert rows[0]["company"] == "Wandb"
    assert rows[0]["role"] == "Founding Designer"


# ---------------------------------------------------------------------------
# import-shortlist
# ---------------------------------------------------------------------------


def test_read_shortlist_warns_on_malformed_row(tmp_path, capsys):
    """A row with the wrong column count is skipped with a stderr warning."""
    shortlist = tmp_path / "shortlist.md"
    shortlist.write_text(
        "| Company | Role | Location | URL | Reason | Status |\n"
        "|---|---|---|---|---|---|\n"
        "| Ramp | Design Engineer | NYC | https://example.com/r1 | ⭐ | pending |\n"
        "| BadRow | only-three | cols |\n"  # 3 cells instead of 6
    )
    rows = read_shortlist(shortlist)
    captured = capsys.readouterr()
    assert len(rows) == 1  # valid row still returned
    assert "WARN" in captured.err
    assert "expected 6 cells" in captured.err
    assert "BadRow" in captured.err


def test_import_shortlist_promotes_new_rows(tmp_path):
    conn = make_db(tmp_path)
    apps = tmp_path / "applications"
    apps.mkdir()
    shortlist = tmp_path / "shortlist.md"
    make_shortlist(shortlist, [
        ("Ramp", "Design Engineer", "NYC", "https://example.com/r1", "⭐", "pending"),
        ("Ramp", "Product Designer", "NYC", "https://example.com/r2", "⭐", "approved"),
        ("Endex", "Founding Designer", "NYC", "https://example.com/e", "⭐", "approved"),
        ("Foo", "PM", "Remote", "https://example.com/f", "-", "dismissed"),
    ])
    summary = import_shortlist(conn, shortlist, apps)
    rows = list_rows(conn)
    assert len(rows) == 3  # Ramp x2 + Endex; dismissed skipped
    assert all(r["stage"] == "Discovered" for r in rows)
    assert summary["imported_rows"] == 3
    assert summary["dismissed_skipped"] == 1


def test_import_shortlist_creates_role_slug_stub_folders(tmp_path):
    conn = make_db(tmp_path)
    apps = tmp_path / "applications"
    apps.mkdir()
    shortlist = tmp_path / "shortlist.md"
    make_shortlist(shortlist, [
        ("Ramp", "Design Engineer", "NYC", "https://example.com/r1", "⭐", "pending"),
        ("Ramp", "Product Designer", "NYC", "https://example.com/r2", "⭐", "approved"),
        ("Endex", "Founding Designer", "NYC", "https://example.com/e", "⭐", "approved"),
        ("Foo", "PM", "Remote", "https://example.com/f", "-", "dismissed"),
    ])
    import_shortlist(conn, shortlist, apps)
    assert (apps / "ramp" / "design-engineer" / "jd.md").exists()
    assert (apps / "ramp" / "product-designer" / "jd.md").exists()
    assert (apps / "endex" / "founding-designer" / "jd.md").exists()
    assert not (apps / "foo").exists()
    assert summary_counts(conn, "ramp") == 2


def summary_counts(conn, co_slug):
    return conn.execute(
        "SELECT COUNT(*) FROM applications WHERE company_slug=?", (co_slug,)
    ).fetchone()[0]


def test_import_shortlist_skips_dismissed_rows(tmp_path):
    conn = make_db(tmp_path)
    apps = tmp_path / "applications"
    apps.mkdir()
    shortlist = tmp_path / "shortlist.md"
    make_shortlist(shortlist, [
        ("DismissedCo", "Designer", "NYC", "https://example.com/d", "-", "dismissed"),
    ])
    summary = import_shortlist(conn, shortlist, apps)
    assert list_rows(conn) == []
    assert summary["dismissed_skipped"] == 1


def test_import_shortlist_skips_already_indexed_pairs(tmp_path):
    conn = make_db(tmp_path)
    apps = tmp_path / "applications"
    apps.mkdir()
    # Pre-seed an existing row at a later stage
    upsert(conn, "OpenRouter", "Product Designer", "Drafts ready", "V2 picked", "Send V2", "2026-04-19")
    shortlist = tmp_path / "shortlist.md"
    make_shortlist(shortlist, [
        ("OpenRouter", "Product Designer", "Remote", "https://example.com/or", "⭐", "approved"),
        ("NewCo", "Designer", "NYC", "https://example.com/n", "⭐", "approved"),
    ])
    summary = import_shortlist(conn, shortlist, apps)
    rows = list_rows(conn)
    openrouter = next(r for r in rows if r["company"] == "OpenRouter")
    assert openrouter["stage"] == "Drafts ready"  # not downgraded
    newco = next(r for r in rows if r["company"] == "NewCo")
    assert newco["stage"] == "Discovered"
    assert summary["imported_rows"] == 1
    assert summary["skipped_already_indexed"] == 1


def test_import_shortlist_preserves_existing_real_jd(tmp_path):
    conn = make_db(tmp_path)
    apps = tmp_path / "applications"
    (apps / "openrouter" / "product-designer").mkdir(parents=True)
    real_jd = apps / "openrouter" / "product-designer" / "jd.md"
    real_jd.write_text("# OpenRouter — Product Designer\n\nFull fetched body.\n")
    shortlist = tmp_path / "shortlist.md"
    make_shortlist(shortlist, [
        ("OpenRouter", "Product Designer", "Remote", "https://example.com/or", "⭐", "approved"),
    ])
    summary = import_shortlist(conn, shortlist, apps)
    assert "Full fetched body." in real_jd.read_text()
    assert summary["preserved_existing_jds"] == 1
    assert summary["created_stubs"] == 0
    assert summary["skipped_already_indexed"] == 0


def test_import_shortlist_stub_content(tmp_path):
    """Each role stub contains the role name and URL."""
    conn = make_db(tmp_path)
    apps = tmp_path / "applications"
    apps.mkdir()
    shortlist = tmp_path / "shortlist.md"
    make_shortlist(shortlist, [
        ("Ramp", "Design Engineer", "NYC", "https://example.com/r1", "⭐", "pending"),
        ("Ramp", "Product Designer", "NYC", "https://example.com/r2", "⭐", "pending"),
    ])
    import_shortlist(conn, shortlist, apps)
    de_stub = (apps / "ramp" / "design-engineer" / "jd.md").read_text()
    pd_stub = (apps / "ramp" / "product-designer" / "jd.md").read_text()
    assert "Design Engineer" in de_stub
    assert "https://example.com/r1" in de_stub
    assert "Product Designer" in pd_stub
    assert "https://example.com/r2" in pd_stub
