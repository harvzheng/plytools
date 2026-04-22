#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# ///
"""
migrate_add_views_table.py — Add the `views` table and seed four starter views.

Step 5 of the SQLite migration plan. Idempotent — safe to run multiple times.

Usage:
    uv run scripts/migrate_add_views_table.py                        # real memory dir
    uv run scripts/migrate_add_views_table.py --memory-dir /tmp/test # override
    uv run scripts/migrate_add_views_table.py --dry-run              # print, no writes
"""
import argparse
import os
import pathlib
import sqlite3
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def default_memory_dir() -> pathlib.Path:
    """Resolve the memory dir from $PLYTOOLS_MEMORY_DIR — no hardcoded default."""
    env = os.environ.get("PLYTOOLS_MEMORY_DIR")
    if not env:
        sys.exit(
            "PLYTOOLS_MEMORY_DIR is not set and no --memory-dir was provided.\n"
            "Set the env var to the directory containing applications.db, "
            "or pass --memory-dir <path>."
        )
    return pathlib.Path(env).expanduser()

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

CREATE_VIEWS_TABLE = """
CREATE TABLE IF NOT EXISTS views (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  sql         TEXT NOT NULL,
  description TEXT,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
"""

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

SEED_VIEWS = [
    {
        "name": "nyc-priority",
        "sql": (
            "SELECT a.*, j.location FROM applications a "
            "LEFT JOIN jd j ON j.application_id = a.id "
            "WHERE j.location LIKE '%New York%' AND a.priority IS NOT NULL "
            "ORDER BY a.priority ASC"
        ),
        "description": "NYC roles ranked by priority (nulls excluded)",
    },
    {
        "name": "replied-stale",
        "sql": (
            "SELECT a.*, j.location FROM applications a "
            "LEFT JOIN jd j ON j.application_id = a.id "
            "WHERE a.stage IN ("
            "'Replied', 'Recruiter screen scheduled', 'Recruiter screen passed', "
            "'HM prelim scheduled', 'HM prelim completed'"
            ") AND julianday('now') - julianday(a.updated) > 14 "
            "ORDER BY a.updated ASC"
        ),
        "description": "Active pipeline rows last touched more than 14 days ago",
    },
    {
        "name": "tier-1-unsent",
        "sql": (
            "SELECT a.*, j.location FROM applications a "
            "LEFT JOIN jd j ON j.application_id = a.id "
            "WHERE a.priority <= 6 AND a.stage = 'Drafts ready' "
            "ORDER BY a.priority ASC"
        ),
        "description": "Priority ≤ 6 roles with drafts ready but not yet sent",
    },
    {
        "name": "fresh-replies",
        "sql": (
            "SELECT a.*, j.location FROM applications a "
            "LEFT JOIN jd j ON j.application_id = a.id "
            "WHERE a.stage IN ("
            "'Replied', 'Recruiter screen scheduled', 'Recruiter screen passed', "
            "'HM prelim scheduled', 'HM prelim completed'"
            ") AND julianday('now') - julianday(a.updated) <= 14 "
            "ORDER BY a.updated DESC"
        ),
        "description": "Active pipeline rows updated within the last 14 days",
    },
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--memory-dir",
        type=pathlib.Path,
        default=None,
        help="Path to the memory directory (default: $PLYTOOLS_MEMORY_DIR)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without writing anything",
    )
    args = parser.parse_args()

    memory_dir = args.memory_dir if args.memory_dir is not None else default_memory_dir()
    db_path = memory_dir / "applications.db"
    if not db_path.exists():
        print(f"ERROR: DB not found at {db_path}", file=sys.stderr)
        print("Run scripts/migrate_to_sqlite.py first.", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print(f"[dry-run] Would open: {db_path}")
        print("[dry-run] Would CREATE TABLE IF NOT EXISTS views (...)")
        for v in SEED_VIEWS:
            print(f"[dry-run] Would INSERT OR IGNORE INTO views name={v['name']!r}")
        print("[dry-run] Done (no writes).")
        return

    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA foreign_keys = ON")

    # Check whether table already existed
    existing = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='views'"
    ).fetchone()

    con.execute(CREATE_VIEWS_TABLE)
    con.commit()

    if existing:
        print("views table already exists — skipping CREATE.")
    else:
        print("Created views table.")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    inserted = 0
    skipped = 0
    for v in SEED_VIEWS:
        result = con.execute(
            """
            INSERT OR IGNORE INTO views (name, sql, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (v["name"], v["sql"], v["description"], now, now),
        )
        if result.rowcount:
            print(f"  Inserted view: {v['name']}")
            inserted += 1
        else:
            print(f"  Skipped (already exists): {v['name']}")
            skipped += 1

    con.commit()
    con.close()

    print(f"\nDone. inserted={inserted} skipped={skipped}")


if __name__ == "__main__":
    main()
