"""
Tests for migrate_to_sqlite.py

Run with: uv run --with pytest pytest tests/test_migrate_to_sqlite.py -v
"""
import importlib.util
import sqlite3
import pathlib

import pytest

# ---------------------------------------------------------------------------
# Bootstrap: load migrate_to_sqlite as a module (it uses a uv shebang, so we
# can't just `import` it normally — we load it via importlib).
# ---------------------------------------------------------------------------

SCRIPTS_DIR = pathlib.Path(__file__).parent.parent / "scripts"
FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures" / "migrate"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "migrate_to_sqlite",
        SCRIPTS_DIR / "migrate_to_sqlite.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load_module()


# ---------------------------------------------------------------------------
# status.md parser
# ---------------------------------------------------------------------------


class TestParseStatus:
    def test_extracts_stage(self):
        text = "- **Stage:** Drafts ready\n- **Priority:** 1\n- **Last action:** Did a thing\n- **Next step:** Do more\n"
        r = m.parse_status(text)
        assert r["stage"] == "Drafts ready"

    def test_extracts_priority_as_int(self):
        text = "- **Stage:** Applied\n- **Priority:** 3\n- **Last action:** x\n- **Next step:** y\n"
        r = m.parse_status(text)
        assert r["priority"] == 3

    def test_extracts_last_action(self):
        text = "- **Stage:** Applied\n- **Last action:** Cold-applied 2026-04-20\n- **Next step:** Wait\n"
        r = m.parse_status(text)
        assert r["last_action"] == "Cold-applied 2026-04-20"

    def test_extracts_next_step(self):
        text = "- **Stage:** Applied\n- **Last action:** x\n- **Next step:** Wait 2-3 weeks\n"
        r = m.parse_status(text)
        assert r["next_step"] == "Wait 2-3 weeks"

    def test_priority_missing_gives_none(self):
        text = "- **Stage:** Discovered\n- **Last action:** x\n- **Next step:** y\n"
        r = m.parse_status(text)
        assert r["priority"] is None

    def test_notes_captures_body_after_bullets(self):
        text = (
            "- **Stage:** Applied\n"
            "- **Priority:** 1\n"
            "- **Last action:** Did a thing\n"
            "- **Next step:** Do more\n"
            "\n"
            "## Fit\n"
            "\n"
            "Strong match.\n"
            "- Point A\n"
            "\n"
            "## Flags\n"
            "\n"
            "- Flag one\n"
        )
        r = m.parse_status(text)
        assert "Fit" in r["notes"]
        assert "Flag one" in r["notes"]
        assert r["stage"] == "Applied"

    def test_notes_is_none_when_no_body(self):
        text = "- **Stage:** Discovered\n- **Last action:** x\n- **Next step:** y\n"
        r = m.parse_status(text)
        assert r["notes"] is None

    def test_stage_missing_defaults_to_discovered(self):
        text = "- **Last action:** x\n- **Next step:** y\n"
        r = m.parse_status(text)
        assert r["stage"] == "Discovered"

    def test_auctor_shape_fit_and_flags_in_notes(self):
        """Inline - **Fit:** and - **Flags:** bullets must land in notes, not be dropped."""
        text = (
            "# Auctor — Product Designer\n"
            "- **Stage:** Applied\n"
            "- **Last action:** Cold-applied 2026-04-21\n"
            "- **Next step:** Wait 2–3 weeks ...\n"
            "- **Fit:** Moderate-to-strong on shape.\n"
            '  - "AI layer for professional services" → /lab AI Pattern Testing.\n'
            "  - JD is unusually short...\n"
            "- **Flags:**\n"
            "  - Comp range $135–220k is wide ...\n"
        )
        r = m.parse_status(text)
        assert r["stage"] == "Applied"
        assert r["last_action"] == "Cold-applied 2026-04-21"
        assert r["notes"] is not None, "notes must not be None — Fit/Flags were dropped"
        assert "Fit:" in r["notes"]
        assert "Flags:" in r["notes"]
        assert "AI layer for professional services" in r["notes"]
        assert "Comp range" in r["notes"]
        assert "unrecognized_keys" in r
        # Fit triggers the flip to body mode; Flags is already in body so only Fit
        # needs to appear in unrecognized_keys.
        assert "Fit" in r["unrecognized_keys"]

    def test_jd_copy_paste_bullets_ignored(self):
        """Compensation/Location/URL/Fetched/Employment bullets must not appear in notes."""
        text = (
            "- **Stage:** Applied\n"
            "- **Compensation:** $100k–$200k\n"
            "- **Location:** Remote\n"
            "- **URL:** https://example.com\n"
            "- **Next step:** Wait\n"
        )
        r = m.parse_status(text)
        assert r["notes"] is None
        assert r["stage"] == "Applied"
        assert r["next_step"] == "Wait"


# ---------------------------------------------------------------------------
# Compensation parser
# ---------------------------------------------------------------------------


class TestParseComp:
    def test_k_range_em_dash(self):
        low, high = m.parse_comp("$100k–$250k")
        assert low == 100_000
        assert high == 250_000

    def test_k_range_hyphen(self):
        low, high = m.parse_comp("$100-250K")
        assert low == 100_000
        assert high == 250_000

    def test_full_dollar_range(self):
        low, high = m.parse_comp("$150,000–$200,000")
        assert low == 150_000
        assert high == 200_000

    def test_mixed_k_and_full(self):
        low, high = m.parse_comp("$172K - $440K")
        assert low == 172_000
        assert high == 440_000

    def test_decimal_k(self):
        # e.g. $143.2K - $284K
        low, high = m.parse_comp("$143.2K - $284K")
        assert low == 143_200
        assert high == 284_000

    def test_comma_in_full(self):
        low, high = m.parse_comp("$174,250 - $205,000")
        assert low == 174_250
        assert high == 205_000

    def test_single_value(self):
        low, high = m.parse_comp("$170,000")
        assert low == 170_000
        assert high is None

    def test_not_listed(self):
        low, high = m.parse_comp("Not listed")
        assert low is None
        assert high is None

    def test_garbage_returns_nulls(self):
        low, high = m.parse_comp("Ask recruiter")
        assert low is None
        assert high is None

    def test_empty_returns_nulls(self):
        low, high = m.parse_comp("")
        assert low is None
        assert high is None

    def test_none_returns_nulls(self):
        low, high = m.parse_comp(None)
        assert low is None
        assert high is None

    def test_range_with_equity_suffix(self):
        low, high = m.parse_comp("$100,000–$250,000 + equity")
        assert low == 100_000
        assert high == 250_000


# ---------------------------------------------------------------------------
# Contacts parser
# ---------------------------------------------------------------------------


class TestParseContacts:
    def test_named_contact_under_warm_header(self):
        text = (
            "# Company — Contacts\n"
            "\n"
            "## Warm\n"
            "\n"
            "### Jane Smith\n"
            "\n"
            "- **Role:** Head of Design\n"
            "- **LinkedIn:** linkedin.com/in/janesmith\n"
            "- **Email:** jane@co.com\n"
        )
        contacts = m.parse_contacts(text)
        assert len(contacts) >= 1
        jane = next((c for c in contacts if c["name"] == "Jane Smith"), None)
        assert jane is not None
        assert jane["tier"] == "warm"
        assert jane["role"] == "Head of Design"
        assert jane["linkedin"] == "linkedin.com/in/janesmith"
        assert jane["email"] == "jane@co.com"

    def test_tier_inferred_from_section_header(self):
        text = (
            "## Cold\n"
            "\n"
            "### Bob Jones\n"
            "\n"
            "- **Role:** Recruiter\n"
        )
        contacts = m.parse_contacts(text)
        bob = next((c for c in contacts if c["name"] == "Bob Jones"), None)
        assert bob is not None
        assert bob["tier"] == "cold"

    def test_multiple_contacts_different_tiers(self):
        text = (
            "## Warm\n"
            "\n"
            "### Alice A\n"
            "\n"
            "- **Role:** Designer\n"
            "\n"
            "## Cold\n"
            "\n"
            "### Charlie C\n"
            "\n"
            "- **Role:** Recruiter\n"
        )
        contacts = m.parse_contacts(text)
        names = {c["name"] for c in contacts}
        assert "Alice A" in names
        assert "Charlie C" in names
        alice = next(c for c in contacts if c["name"] == "Alice A")
        charlie = next(c for c in contacts if c["name"] == "Charlie C")
        assert alice["tier"] == "warm"
        assert charlie["tier"] == "cold"

    def test_empty_file_returns_empty_list(self):
        contacts = m.parse_contacts("")
        assert contacts == []

    def test_no_named_contacts_returns_synthetic_row(self):
        text = "Some freeform text with no structured contacts.\nJust a note about someone."
        contacts = m.parse_contacts(text)
        assert len(contacts) == 1
        assert contacts[0]["name"] == "(unparsed notes)"
        assert "freeform" in contacts[0]["notes"]

    def test_semi_warm_tier(self):
        text = (
            "## Semi-warm\n"
            "\n"
            "### Dave D\n"
            "\n"
            "- **Role:** Engineer\n"
        )
        contacts = m.parse_contacts(text)
        dave = next((c for c in contacts if c["name"] == "Dave D"), None)
        assert dave is not None
        assert dave["tier"] == "semi-warm"


# ---------------------------------------------------------------------------
# Frontmatter parser
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    def test_extracts_persona(self):
        text = "---\npersona: hiring-manager\nvariant: initial\ntarget: Jane <jane@co.com>\n---\nBody text"
        fm = m.parse_frontmatter(text)
        assert fm["persona"] == "hiring-manager"

    def test_extracts_variant(self):
        text = "---\npersona: ceo\nvariant: linkedin\ntarget: Someone\n---\n"
        fm = m.parse_frontmatter(text)
        assert fm["variant"] == "linkedin"

    def test_extracts_target(self):
        text = "---\ntarget: John Doe\n---\n"
        fm = m.parse_frontmatter(text)
        assert fm["target"] == "John Doe"

    def test_no_frontmatter_returns_empty(self):
        text = "# Just a normal markdown file\n\nNo frontmatter here."
        fm = m.parse_frontmatter(text)
        assert fm == {}

    def test_missing_keys_are_none(self):
        text = "---\npersona: ceo\n---\n"
        fm = m.parse_frontmatter(text)
        assert fm["persona"] == "ceo"
        assert fm.get("variant") is None
        assert fm.get("target") is None


# ---------------------------------------------------------------------------
# index.md parser
# ---------------------------------------------------------------------------


class TestParseIndex:
    def test_parses_rows(self):
        text = (
            "| Company | Role | Stage | Last action | Next | Updated |\n"
            "|---|---|---|---|---|---|\n"
            "| Acme | Designer | Applied | Cold-applied | Wait | 2026-04-20 |\n"
            "| Beta Co | Engineer | Discovered | JD ingested | Review | 2026-04-19 |\n"
        )
        rows = m.parse_index(text)
        assert len(rows) == 2
        assert rows[0]["company"] == "Acme"
        assert rows[0]["role"] == "Designer"
        assert rows[0]["stage"] == "Applied"
        assert rows[0]["updated"] == "2026-04-20"

    def test_skips_header_and_separator(self):
        text = (
            "| Company | Role | Stage | Last action | Next | Updated |\n"
            "|---|---|---|---|---|---|\n"
            "| Acme | Designer | Applied | Cold | Wait | 2026-04-21 |\n"
        )
        rows = m.parse_index(text)
        assert len(rows) == 1

    def test_company_to_slug(self):
        text = (
            "| Company | Role | Stage | Last action | Next | Updated |\n"
            "|---|---|---|---|---|---|\n"
            "| My Cool Co | Senior Designer | Discovered | x | y | 2026-04-19 |\n"
        )
        rows = m.parse_index(text)
        assert rows[0]["company_slug"] == "my-cool-co"
        assert rows[0]["role_slug"] == "senior-designer"


# ---------------------------------------------------------------------------
# End-to-end: fixture memory dir
# ---------------------------------------------------------------------------


class TestEndToEnd:
    @pytest.fixture
    def memory_dir(self):
        return FIXTURES_DIR / "memory"

    @pytest.fixture
    def db_path(self, tmp_path):
        return tmp_path / "applications.db"

    @pytest.fixture
    def report_path(self, tmp_path):
        return tmp_path / "_migration_report.md"

    def test_application_row_counts(self, memory_dir, db_path, report_path):
        m.run_migration(
            memory_dir=memory_dir,
            db_path=db_path,
            report_path=report_path,
            dry_run=False,
        )
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        conn.close()
        # index has 3 rows + 1 orphan folder = 4 total
        assert count == 4

    def test_jd_rows_inserted(self, memory_dir, db_path, report_path):
        m.run_migration(
            memory_dir=memory_dir,
            db_path=db_path,
            report_path=report_path,
            dry_run=False,
        )
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM jd").fetchone()[0]
        conn.close()
        # role-alpha and role-beta each have a jd.md
        assert count == 2

    def test_contacts_rows_inserted(self, memory_dir, db_path, report_path):
        m.run_migration(
            memory_dir=memory_dir,
            db_path=db_path,
            report_path=report_path,
            dry_run=False,
        )
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        conn.close()
        # role-alpha has 2 named contacts (Jane + Bob)
        assert count >= 2

    def test_drafts_rows_inserted(self, memory_dir, db_path, report_path):
        m.run_migration(
            memory_dir=memory_dir,
            db_path=db_path,
            report_path=report_path,
            dry_run=False,
        )
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]
        conn.close()
        # role-alpha has 1 draft
        assert count == 1

    def test_draft_frontmatter_parsed(self, memory_dir, db_path, report_path):
        m.run_migration(
            memory_dir=memory_dir,
            db_path=db_path,
            report_path=report_path,
            dry_run=False,
        )
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT persona, variant, target FROM drafts WHERE name='cover-letter'"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "hiring-manager"
        assert row[1] == "initial"
        assert "Jane Smith" in row[2]

    def test_orphan_folder_row_has_folder_only_stage(self, memory_dir, db_path, report_path):
        m.run_migration(
            memory_dir=memory_dir,
            db_path=db_path,
            report_path=report_path,
            dry_run=False,
        )
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT stage FROM applications WHERE company_slug='orphan-folder'"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "Folder only"

    def test_index_only_row_present(self, memory_dir, db_path, report_path):
        m.run_migration(
            memory_dir=memory_dir,
            db_path=db_path,
            report_path=report_path,
            dry_run=False,
        )
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT stage FROM applications WHERE company_slug='index-only-co'"
        ).fetchone()
        conn.close()
        assert row is not None
        # stage from index.md
        assert row[0] == "Discovered"

    def test_report_written(self, memory_dir, db_path, report_path):
        m.run_migration(
            memory_dir=memory_dir,
            db_path=db_path,
            report_path=report_path,
            dry_run=False,
        )
        assert report_path.exists()
        content = report_path.read_text()
        assert "applications" in content.lower()

    def test_dry_run_writes_no_db(self, memory_dir, db_path, report_path):
        m.run_migration(
            memory_dir=memory_dir,
            db_path=db_path,
            report_path=report_path,
            dry_run=True,
        )
        assert not db_path.exists()

    def test_force_flag_overwrites_existing_db(self, memory_dir, db_path, report_path):
        # First run
        m.run_migration(
            memory_dir=memory_dir,
            db_path=db_path,
            report_path=report_path,
            dry_run=False,
        )
        # Second run without force should raise
        with pytest.raises(SystemExit):
            m.run_migration(
                memory_dir=memory_dir,
                db_path=db_path,
                report_path=report_path,
                dry_run=False,
                force=False,
            )
        # Second run with force should succeed
        m.run_migration(
            memory_dir=memory_dir,
            db_path=db_path,
            report_path=report_path,
            dry_run=False,
            force=True,
        )
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        conn.close()
        assert count == 4

    def test_comp_low_high_parsed(self, memory_dir, db_path, report_path):
        m.run_migration(
            memory_dir=memory_dir,
            db_path=db_path,
            report_path=report_path,
            dry_run=False,
        )
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            """
            SELECT j.comp_low, j.comp_high
            FROM jd j
            JOIN applications a ON a.id = j.application_id
            WHERE a.company_slug = 'role-alpha'
            """
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == 150_000
        assert row[1] == 200_000

    def test_not_listed_comp_gives_nulls(self, memory_dir, db_path, report_path):
        m.run_migration(
            memory_dir=memory_dir,
            db_path=db_path,
            report_path=report_path,
            dry_run=False,
        )
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            """
            SELECT j.comp_low, j.comp_high, j.compensation_raw
            FROM jd j
            JOIN applications a ON a.id = j.application_id
            WHERE a.company_slug = 'role-beta'
            """
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] is None
        assert row[1] is None
        assert row[2] == "Not listed"


# ---------------------------------------------------------------------------
# Schema / connection: FK cascade
# ---------------------------------------------------------------------------


class TestForeignKeyCascade:
    def test_delete_application_cascades_to_drafts(self, tmp_path):
        """ON DELETE CASCADE must work on any connection opened via open_db()."""
        db_path = tmp_path / "fk_test.db"

        # Seed: insert an application + a linked drafts row, then close.
        conn1 = m.open_db(db_path)
        with conn1:
            conn1.execute(
                """
                INSERT INTO applications
                  (company_slug, role_slug, company, role, stage, updated, created_at)
                VALUES ('test-co', 'test-role', 'Test Co', 'Test Role',
                        'Discovered', '2026-04-21', '2026-04-21')
                """
            )
            app_id = conn1.execute(
                "SELECT id FROM applications WHERE company_slug='test-co'"
            ).fetchone()[0]
            conn1.execute(
                """
                INSERT INTO drafts (application_id, path, name, updated_at)
                VALUES (?, '/tmp/cover.md', 'cover', '2026-04-21T00:00:00+00:00')
                """,
                (app_id,),
            )
        conn1.close()

        # Re-open via open_db (fresh connection) and delete the parent row.
        conn2 = m.open_db(db_path)
        with conn2:
            conn2.execute("DELETE FROM applications WHERE id = ?", (app_id,))
        conn2.close()

        # Verify cascade: drafts row must be gone.
        conn3 = m.open_db(db_path)
        draft_count = conn3.execute(
            "SELECT COUNT(*) FROM drafts WHERE application_id = ?", (app_id,)
        ).fetchone()[0]
        conn3.close()

        assert draft_count == 0, (
            "Expected drafts row to be deleted via ON DELETE CASCADE, "
            f"but found {draft_count} row(s) still present."
        )
