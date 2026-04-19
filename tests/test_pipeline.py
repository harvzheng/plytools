"""Tests for pipeline.py — application index read/append/upsert/reconcile."""
from __future__ import annotations
import pathlib
import pytest

from pipeline import Row, append_row, read_index, render_index, upsert_row, reconcile, read_shortlist, import_shortlist


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


def test_upsert_appends_when_no_match(tmp_path: pathlib.Path):
    path = tmp_path / "index.md"
    row = Row("OpenRouter", "Product Designer", "Discovered", "JD ingested",
              "Pull contacts", "2026-04-19")
    upsert_row(path, row)
    rows = read_index(path)
    assert len(rows) == 1
    assert rows[0].stage == "Discovered"


def test_upsert_replaces_when_company_role_match(tmp_path: pathlib.Path):
    path = tmp_path / "index.md"
    r1 = Row("OpenRouter", "Product Designer", "Discovered", "JD ingested",
             "Pull contacts", "2026-04-19")
    r2 = Row("OpenRouter", "Product Designer", "Drafts ready",
             "V2 picked", "Send V2", "2026-04-19")
    upsert_row(path, r1)
    upsert_row(path, r2)
    rows = read_index(path)
    assert len(rows) == 1
    assert rows[0].stage == "Drafts ready"
    assert rows[0].last_action == "V2 picked"


def test_upsert_distinguishes_different_roles_at_same_company(tmp_path):
    path = tmp_path / "index.md"
    upsert_row(path, Row("Foo", "Designer", "Discovered", "-", "-", "2026-04-19"))
    upsert_row(path, Row("Foo", "Engineer", "Discovered", "-", "-", "2026-04-19"))
    rows = read_index(path)
    assert len(rows) == 2


def test_reconcile_creates_rows_for_orphan_folders(tmp_path: pathlib.Path):
    apps = tmp_path / "applications"
    (apps / "stainless").mkdir(parents=True)
    (apps / "stainless" / "status.md").write_text(
        "# Status — Stainless, Product Designer\n\n"
        "- **Stage:** Contacts tiered\n"
        "- **Role:** Product Designer\n"
        "- **Last action:** Tiered candidates\n"
        "- **Next step:** Pick target\n"
    )
    (apps / "_triage").mkdir()  # underscore-prefixed: must be skipped
    index = apps / "index.md"
    reconcile(index, apps)
    rows = read_index(index)
    assert len(rows) == 1
    assert rows[0].company == "Stainless"
    assert rows[0].role == "Product Designer"
    assert rows[0].stage == "Contacts tiered"


def test_reconcile_is_idempotent(tmp_path: pathlib.Path):
    apps = tmp_path / "applications"
    (apps / "wandb").mkdir(parents=True)
    (apps / "wandb" / "status.md").write_text(
        "# Status — Weights & Biases (Weave), Senior Product Designer\n\n"
        "- **Stage:** JD ingested\n"
        "- **Role:** Senior Product Designer, Weave\n"
    )
    index = apps / "index.md"
    reconcile(index, apps)
    first = read_index(index)
    reconcile(index, apps)
    second = read_index(index)
    assert first == second


def test_upsert_dedupes_existing_duplicate_rows(tmp_path: pathlib.Path):
    path = tmp_path / "index.md"
    # Seed two rows with the same (company, role) — the broken state we want
    # upsert to clean up.
    append_row(path, Row("OpenRouter", "Product Designer", "Discovered",
                         "JD ingested", "Pull contacts", "2026-04-19"))
    append_row(path, Row("OpenRouter", "Product Designer", "Drafts ready",
                         "V2 picked", "Send V2", "2026-04-19"))
    assert len(read_index(path)) == 2
    upsert_row(path, Row("OpenRouter", "Product Designer", "Sent",
                         "Sent V2", "Wait for reply", "2026-04-20"))
    rows = read_index(path)
    assert len(rows) == 1
    assert rows[0].stage == "Sent"


def test_reconcile_role_strips_parenthetical_qualifiers(tmp_path: pathlib.Path):
    apps = tmp_path / "applications"
    (apps / "stainless").mkdir(parents=True)
    (apps / "stainless" / "status.md").write_text(
        "# Status — Stainless, Product Designer\n\n"
        "- **Stage:** Contacts tiered\n"
        "- **Role:** Product Designer (first dedicated, product + brand)\n"
    )
    index = apps / "index.md"
    reconcile(index, apps)
    rows = read_index(index)
    assert rows[0].role == "Product Designer"


def test_read_shortlist_parses_non_dismissed_rows(tmp_path: pathlib.Path):
    path = tmp_path / "shortlist.md"
    path.write_text(
        "| Company | Role | Location | URL | Reason | Status |\n"
        "|---|---|---|---|---|---|\n"
        "| Ramp | Design Engineer | NYC | https://example.com/r1 | ⭐ | pending |\n"
        "| Ramp | Product Designer | NYC | https://example.com/r2 | ⭐ | approved |\n"
        "| Foo | PM | Remote | https://example.com/f | - | dismissed |\n"
    )
    rows = read_shortlist(path)
    assert len(rows) == 3
    assert rows[0].company == "Ramp"
    assert rows[1].role == "Product Designer"
    assert rows[2].status == "dismissed"


def test_import_shortlist_upserts_rows_and_creates_stubs(tmp_path: pathlib.Path):
    apps = tmp_path / "applications"
    apps.mkdir()
    shortlist = apps / "_shortlist.md"
    shortlist.write_text(
        "| Company | Role | Location | URL | Reason | Status |\n"
        "|---|---|---|---|---|---|\n"
        "| Ramp | Design Engineer | NYC | https://example.com/r1 | ⭐ | pending |\n"
        "| Ramp | Product Designer | NYC | https://example.com/r2 | ⭐ | approved |\n"
        "| Endex | Founding Designer | NYC | https://example.com/e | ⭐ | approved |\n"
        "| Foo | PM | Remote | https://example.com/f | - | dismissed |\n"
    )
    index = apps / "index.md"
    summary = import_shortlist(index, shortlist, apps)
    rows = read_index(index)
    assert len(rows) == 3  # two Ramp roles + one Endex; dismissed skipped
    stages = {r.stage for r in rows}
    assert stages == {"Discovered"}
    assert (apps / "ramp" / "jd.md").exists()
    assert (apps / "endex" / "jd.md").exists()
    assert not (apps / "foo").exists()
    assert summary["imported_rows"] == 3
    assert summary["created_stubs"] == 2
    assert summary["dismissed_skipped"] == 1


def test_import_shortlist_preserves_existing_real_jd(tmp_path: pathlib.Path):
    apps = tmp_path / "applications"
    (apps / "openrouter").mkdir(parents=True)
    real_jd = apps / "openrouter" / "jd.md"
    real_jd.write_text("# OpenRouter — Product Designer\n\nFull fetched body.\n")

    shortlist = apps / "_shortlist.md"
    shortlist.write_text(
        "| Company | Role | Location | URL | Reason | Status |\n"
        "|---|---|---|---|---|---|\n"
        "| OpenRouter | Product Designer | Remote | https://example.com/or | ⭐ | approved |\n"
    )
    index = apps / "index.md"
    summary = import_shortlist(index, shortlist, apps)
    # existing JD body must be untouched
    assert "Full fetched body." in real_jd.read_text()
    assert summary["preserved_existing_jds"] == 1
    assert summary["created_stubs"] == 0


def test_import_shortlist_stub_lists_all_roles_at_same_company(tmp_path: pathlib.Path):
    apps = tmp_path / "applications"
    apps.mkdir()
    shortlist = apps / "_shortlist.md"
    shortlist.write_text(
        "| Company | Role | Location | URL | Reason | Status |\n"
        "|---|---|---|---|---|---|\n"
        "| Ramp | Design Engineer | NYC | https://example.com/r1 | ⭐ | pending |\n"
        "| Ramp | Product Designer | NYC | https://example.com/r2 | ⭐ | pending |\n"
        "| Ramp | Frontend Eng | NYC | https://example.com/r3 | ⭐ | pending |\n"
    )
    import_shortlist(apps / "index.md", shortlist, apps)
    stub = (apps / "ramp" / "jd.md").read_text()
    assert "Design Engineer" in stub
    assert "Product Designer" in stub
    assert "Frontend Eng" in stub
    assert "https://example.com/r1" in stub
