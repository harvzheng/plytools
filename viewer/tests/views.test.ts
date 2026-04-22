import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import Database from "better-sqlite3";
import {
  validateViewSql,
  ViewSqlError,
  listViews,
  runView,
  createOrUpdateView,
  deleteView,
  closeReadOnlyHandles,
} from "../server/views";

// ---------------------------------------------------------------------------
// Schema (minimal — only what views.ts needs)
// ---------------------------------------------------------------------------

const SCHEMA = `
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

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

CREATE TABLE IF NOT EXISTS jd (
  application_id   INTEGER PRIMARY KEY REFERENCES applications(id) ON DELETE CASCADE,
  url              TEXT,
  location         TEXT,
  employment       TEXT,
  compensation_raw TEXT,
  comp_low         INTEGER,
  comp_high        INTEGER,
  fetched_at       TEXT,
  body_path        TEXT
);

CREATE TABLE IF NOT EXISTS views (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  sql         TEXT NOT NULL,
  description TEXT,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
`;

let root: string;
let dbPath: string;
let db: Database.Database;

function openTestDb(path: string): Database.Database {
  const d = new Database(path);
  d.exec(SCHEMA);
  return d;
}

function seedViews(d: Database.Database) {
  const now = "2026-04-21T00:00:00Z";
  d.prepare(
    "INSERT OR IGNORE INTO views (name, sql, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)"
  ).run(
    "all-apps",
    "SELECT a.*, j.location FROM applications a LEFT JOIN jd j ON j.application_id = a.id ORDER BY a.priority ASC",
    "All applications ordered by priority",
    now,
    now
  );
  d.prepare(
    "INSERT OR IGNORE INTO views (name, sql, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)"
  ).run(
    "high-priority",
    "SELECT a.*, j.location FROM applications a LEFT JOIN jd j ON j.application_id = a.id WHERE a.priority <= 3 ORDER BY a.priority ASC",
    "Priority 3 and under",
    now,
    now
  );
}

function seedApplications(d: Database.Database) {
  const now = "2026-04-21T00:00:00Z";
  const r = d.prepare(
    `INSERT INTO applications (company_slug, role_slug, company, role, stage, priority, last_action, next_step, updated, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  ).run("acme-inc", "ux-engineer", "Acme Inc", "UX Engineer", "Applied", 1, "Submitted", "Wait", "2026-04-20", now);

  d.prepare(
    `INSERT INTO jd (application_id, url, location) VALUES (?, ?, ?)`
  ).run(r.lastInsertRowid, "https://acme.com", "New York, NY");

  d.prepare(
    `INSERT INTO applications (company_slug, role_slug, company, role, stage, priority, last_action, next_step, updated, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  ).run("beta-co", "product-designer", "Beta Co", "Product Designer", "Drafts ready", 5, "V1 ready", "Send", "2026-04-19", now);
}

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "views-test-"));
  dbPath = join(root, "applications.db");
  db = openTestDb(dbPath);
  seedViews(db);
  seedApplications(db);
});

afterEach(() => {
  closeReadOnlyHandles();
  try { db.close(); } catch { /* ignore */ }
  rmSync(root, { recursive: true, force: true });
});

// ---------------------------------------------------------------------------
// validateViewSql
// ---------------------------------------------------------------------------

describe("validateViewSql", () => {
  it("accepts a plain SELECT", () => {
    expect(() => validateViewSql("SELECT * FROM applications")).not.toThrow();
  });

  it("accepts a SELECT with trailing semicolon stripped", () => {
    expect(() => validateViewSql("SELECT * FROM applications;")).not.toThrow();
  });

  it("accepts a CTE (WITH ... SELECT)", () => {
    expect(() =>
      validateViewSql("WITH cte AS (SELECT * FROM applications) SELECT * FROM cte")
    ).not.toThrow();
  });

  it("accepts SELECT with leading line comment", () => {
    expect(() =>
      validateViewSql("-- find all\nSELECT * FROM applications")
    ).not.toThrow();
  });

  it("accepts SELECT with leading block comment", () => {
    expect(() =>
      validateViewSql("/* find all */ SELECT * FROM applications")
    ).not.toThrow();
  });

  it("rejects DROP TABLE", () => {
    expect(() => validateViewSql("DROP TABLE applications")).toThrow(ViewSqlError);
  });

  it("rejects UPDATE", () => {
    expect(() => validateViewSql("UPDATE applications SET stage='Applied'")).toThrow(ViewSqlError);
  });

  it("rejects INSERT", () => {
    expect(() => validateViewSql("INSERT INTO applications VALUES (1)")).toThrow(ViewSqlError);
  });

  it("rejects DELETE", () => {
    expect(() => validateViewSql("DELETE FROM applications")).toThrow(ViewSqlError);
  });

  it("rejects multi-statement (semicolon in middle)", () => {
    expect(() =>
      validateViewSql("SELECT * FROM applications; DROP TABLE applications")
    ).toThrow(ViewSqlError);
  });

  it("allows semicolons inside string literals", () => {
    expect(() =>
      validateViewSql("SELECT * FROM applications WHERE notes = 'a;b'")
    ).not.toThrow();
  });

  it("rejects empty string", () => {
    expect(() => validateViewSql("")).toThrow(ViewSqlError);
  });

  it("rejects whitespace only", () => {
    expect(() => validateViewSql("   ")).toThrow(ViewSqlError);
  });

  // --- state-machine correctness ---

  it("rejects bypass: SELECT 'x--' ; DROP TABLE t", () => {
    expect(() => validateViewSql("SELECT 'x--' ; DROP TABLE t")).toThrow(ViewSqlError);
  });

  it("accepts false-positive: SELECT * FROM t WHERE notes LIKE '%--%'", () => {
    expect(() =>
      validateViewSql("SELECT * FROM t WHERE notes LIKE '%--%'")
    ).not.toThrow();
  });

  it("accepts escaped single-quote: SELECT 'O''Brien' FROM t", () => {
    expect(() => validateViewSql("SELECT 'O''Brien' FROM t")).not.toThrow();
  });

  it("accepts block comment containing semicolon: SELECT 1 /* ; */ FROM t", () => {
    expect(() => validateViewSql("SELECT 1 /* ; */ FROM t")).not.toThrow();
  });

  it("rejects unterminated block comment", () => {
    expect(() => validateViewSql("SELECT 1 /* start of comment")).toThrow(ViewSqlError);
  });

  it("accepts WITH RECURSIVE CTE", () => {
    expect(() =>
      validateViewSql("WITH RECURSIVE x AS (SELECT 1) SELECT * FROM x")
    ).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// listViews
// ---------------------------------------------------------------------------

describe("listViews", () => {
  it("returns all seeded views", () => {
    const views = listViews(db);
    expect(views.length).toBe(2);
    const names = views.map((v) => v.name);
    expect(names).toContain("all-apps");
    expect(names).toContain("high-priority");
  });

  it("returns correct shape", () => {
    const views = listViews(db);
    const v = views.find((x) => x.name === "all-apps")!;
    expect(v.id).toBeTypeOf("number");
    expect(v.name).toBe("all-apps");
    expect(v.sql).toBeTypeOf("string");
    expect(v.description).toBe("All applications ordered by priority");
    expect(v.createdAt).toBeTypeOf("string");
    expect(v.updatedAt).toBeTypeOf("string");
  });
});

// ---------------------------------------------------------------------------
// runView
// ---------------------------------------------------------------------------

describe("runView", () => {
  it("returns rows for a valid view", async () => {
    const rows = await runView(db, dbPath, "all-apps");
    expect(rows).not.toBeNull();
    expect(rows!.length).toBe(2);
  });

  it("returns IndexRow shape", async () => {
    const rows = await runView(db, dbPath, "all-apps");
    const row = rows![0]!;
    expect(row).toHaveProperty("id");
    expect(row).toHaveProperty("companySlug");
    expect(row).toHaveProperty("roleSlug");
    expect(row).toHaveProperty("company");
    expect(row).toHaveProperty("role");
    expect(row).toHaveProperty("stage");
    expect(row).toHaveProperty("priority");
    expect(row).toHaveProperty("lastAction");
    expect(row).toHaveProperty("nextStep");
    expect(row).toHaveProperty("updated");
    expect(row).toHaveProperty("location");
  });

  it("respects the view's WHERE clause", async () => {
    const rows = await runView(db, dbPath, "high-priority");
    // Only acme-inc (priority 1) should match; beta-co (priority 5) should not
    expect(rows).not.toBeNull();
    expect(rows!.length).toBe(1);
    expect(rows![0]!.companySlug).toBe("acme-inc");
  });

  it("returns null for an unknown view name", async () => {
    const rows = await runView(db, dbPath, "does-not-exist");
    expect(rows).toBeNull();
  });

  it("fills missing columns with defaults (location from jd join)", async () => {
    const rows = await runView(db, dbPath, "all-apps");
    const acme = rows!.find((r) => r.companySlug === "acme-inc")!;
    expect(acme.location).toBe("New York, NY");
  });

  it("throws ViewSqlError when query exceeds 500ms timeout", async () => {
    // Insert an infinite-recursive view directly (bypasses validator).
    const now = "2026-04-21T00:00:00Z";
    db.prepare(
      "INSERT INTO views (name, sql, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)"
    ).run(
      "slow-view",
      "WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM r) SELECT * FROM r LIMIT 1000000",
      "intentionally slow",
      now,
      now
    );
    await expect(runView(db, dbPath, "slow-view")).rejects.toThrow(ViewSqlError);
  }, 10000);
});

// ---------------------------------------------------------------------------
// createOrUpdateView / deleteView
// ---------------------------------------------------------------------------

describe("createOrUpdateView", () => {
  it("creates a new view and returns it", () => {
    const v = createOrUpdateView(db, "test-view", "SELECT * FROM applications", "Test");
    expect(v.name).toBe("test-view");
    expect(v.description).toBe("Test");
    expect(v.id).toBeTypeOf("number");

    const all = listViews(db);
    expect(all.find((x) => x.name === "test-view")).toBeDefined();
  });

  it("updates an existing view", () => {
    createOrUpdateView(db, "test-view", "SELECT * FROM applications", "v1");
    const updated = createOrUpdateView(db, "test-view", "SELECT id FROM applications", "v2");
    expect(updated.sql).toBe("SELECT id FROM applications");
    expect(updated.description).toBe("v2");

    // Still only one row with that name
    const all = listViews(db);
    expect(all.filter((x) => x.name === "test-view").length).toBe(1);
  });

  it("throws ViewSqlError for invalid SQL", () => {
    expect(() =>
      createOrUpdateView(db, "bad-view", "DROP TABLE applications")
    ).toThrow(ViewSqlError);
  });
});

describe("deleteView", () => {
  it("removes an existing view and returns true", () => {
    const result = deleteView(db, "all-apps");
    expect(result).toBe(true);
    expect(listViews(db).find((v) => v.name === "all-apps")).toBeUndefined();
  });

  it("returns false for a non-existent view", () => {
    const result = deleteView(db, "does-not-exist");
    expect(result).toBe(false);
  });
});
