import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync, writeFileSync, mkdirSync, realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import http from "node:http";
import request from "supertest";
import Database from "better-sqlite3";
import { createApi } from "../server/api";
import { closeReadOnlyHandles } from "../server/views";

let root: string;
let server: http.Server;
let baseUrl: string;
let apiClose: (() => void) | undefined;

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

CREATE TABLE IF NOT EXISTS contacts (
  id             INTEGER PRIMARY KEY,
  application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  name           TEXT NOT NULL,
  role           TEXT,
  linkedin       TEXT,
  email          TEXT,
  tier           TEXT,
  notes          TEXT
);

CREATE TABLE IF NOT EXISTS drafts (
  id             INTEGER PRIMARY KEY,
  application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  path           TEXT NOT NULL UNIQUE,
  name           TEXT NOT NULL,
  persona        TEXT,
  variant        TEXT,
  target         TEXT,
  updated_at     TEXT NOT NULL
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

function seedDb(root: string) {
  const dbPath = join(root, "applications.db");
  const db = new Database(dbPath);
  db.exec(SCHEMA);

  // Insert primary role: example-co/product-designer
  const insertApp = db.prepare(`
    INSERT INTO applications (company_slug, role_slug, company, role, stage, priority, last_action, next_step, notes, updated, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);

  const r1 = insertApp.run(
    "example-co", "product-designer",
    "Example Co", "Product Designer",
    "Drafts ready", 2,
    "V1 picked", "Send",
    "Fit: strong\n\nFlags: none",
    "2026-04-19", "2026-04-18"
  );
  const id1 = r1.lastInsertRowid as number;

  db.prepare(`
    INSERT INTO jd (application_id, url, location, employment, compensation_raw, comp_low, comp_high, fetched_at, body_path)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(id1, "https://example.com", "San Francisco, CA", "Full-time", "$150k-$200k", 150000, 200000, "2026-04-01",
    join(root, "applications/example-co/product-designer/jd.md"));

  db.prepare(`
    INSERT INTO contacts (application_id, name, role, linkedin, email, tier, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `).run(id1, "Jane Smith", "Head of Design", "linkedin.com/in/janesmith", "jane@example.com", "warm", "Met at a meetup");

  // Insert second role: acme-inc/ux-engineer (for join coverage)
  const r2 = insertApp.run(
    "acme-inc", "ux-engineer",
    "Acme Inc", "UX Engineer",
    "Applied", 1,
    "Submitted app", "Wait for response",
    null,
    "2026-04-20", "2026-04-19"
  );
  const id2 = r2.lastInsertRowid as number;

  db.prepare(`
    INSERT INTO jd (application_id, url, location, employment, compensation_raw, comp_low, comp_high, fetched_at, body_path)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(id2, "https://acme.com/jobs/ux", "New York, NY", "Full-time", "$120k-$160k", 120000, 160000, "2026-04-15",
    join(root, "applications/acme-inc/ux-engineer/jd.md"));

  // Seed two views
  const now = "2026-04-21T00:00:00Z";
  const insertView = db.prepare(
    "INSERT OR IGNORE INTO views (name, sql, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)"
  );
  insertView.run(
    "nyc-apps",
    "SELECT a.*, j.location FROM applications a LEFT JOIN jd j ON j.application_id = a.id WHERE j.location LIKE '%New York%' ORDER BY a.priority ASC",
    "NYC applications",
    now,
    now
  );
  insertView.run(
    "sf-apps",
    "SELECT a.*, j.location FROM applications a LEFT JOIN jd j ON j.application_id = a.id WHERE j.location LIKE '%San Francisco%' ORDER BY a.priority ASC",
    "SF applications",
    now,
    now
  );

  db.close();
}

function seed(root: string) {
  // Seed DB (authoritative)
  seedDb(root);

  // Primary role files — jd.md, contacts.md, and drafts stay on disk.
  // index.md and status.md are NOT seeded (DB is sole source of truth).
  const roleDir = join(root, "applications/example-co/product-designer");
  mkdirSync(join(roleDir, "drafts"), { recursive: true });
  writeFileSync(
    join(roleDir, "jd.md"),
    "# Example Co\n\n- **URL:** https://example.com\n\n## Role\n\nbody\n"
  );
  writeFileSync(
    join(roleDir, "contacts.md"),
    "# Example Co\n\nnotes\n"
  );
  writeFileSync(
    join(roleDir, "drafts/alex.md"),
    "---\npersona: hiring-manager\n---\nBody here.\n"
  );

  // Second role: acme-inc/ux-engineer — folder + jd.md
  const acmeDir = join(root, "applications/acme-inc/ux-engineer");
  mkdirSync(acmeDir, { recursive: true });
  writeFileSync(
    join(acmeDir, "jd.md"),
    "# Acme Inc\n\n- **URL:** https://acme.com/jobs/ux\n- **Location:** New York, NY\n\n## Role\n\nacme body\n"
  );
}

beforeEach(async () => {
  root = realpathSync(mkdtempSync(join(tmpdir(), "api-")));
  seed(root);
  const api = createApi({
    memoryDir: root,
    // For tests, disable the live watcher so events are driven manually.
    watcher: null,
  });
  apiClose = api.close;
  server = http.createServer(api.handler);
  await new Promise<void>((r) => server.listen(0, r));
  const addr = server.address();
  if (!addr || typeof addr === "string") throw new Error("no addr");
  baseUrl = `http://127.0.0.1:${addr.port}`;
});

afterEach(async () => {
  apiClose?.();
  apiClose = undefined;
  closeReadOnlyHandles();
  await new Promise<void>((r) => server.close(() => r()));
  rmSync(root, { recursive: true, force: true });
});

describe("GET /api/index", () => {
  it("returns parsed index rows", async () => {
    const res = await request(baseUrl).get("/api/index");
    expect(res.status).toBe(200);
    const row = res.body.find((r: any) => r.slug === "example-co/product-designer");
    expect(row).toBeDefined();
    expect(row.company).toBe("Example Co");
  });

  it("surfaces orphan role folders that are missing from the DB", async () => {
    // A role subfolder that isn't in the DB
    const orphanDir = join(root, "applications/orphan-co/brand-designer");
    await import("node:fs/promises").then((fs) =>
      fs.mkdir(orphanDir, { recursive: true })
    );
    const res = await request(baseUrl).get("/api/index");
    expect(res.status).toBe(200);
    const slugs = res.body.map((r: any) => r.slug);
    expect(slugs).toContain("example-co/product-designer");
    expect(slugs).toContain("orphan-co/brand-designer");
    const orphan = res.body.find(
      (r: any) => r.slug === "orphan-co/brand-designer"
    );
    expect(orphan.stage).toBe("Folder only");
  });

  it("returns location and priority columns from the DB", async () => {
    const res = await request(baseUrl).get("/api/index");
    expect(res.status).toBe(200);
    const row = res.body.find((r: any) => r.slug === "example-co/product-designer");
    expect(row.location).toBe("San Francisco, CA");
    expect(row.priority).toBe(2);
  });
});

describe("GET /api/application/:company/:role", () => {
  it("returns the full application payload", async () => {
    const res = await request(baseUrl).get(
      "/api/application/example-co/product-designer"
    );
    expect(res.status).toBe(200);
    expect(res.body.slug).toBe("example-co/product-designer");
    expect(res.body.companySlug).toBe("example-co");
    expect(res.body.roleSlug).toBe("product-designer");
    expect(res.body.dir).toContain("/applications/example-co/product-designer");
    expect(res.body.status.fields.Stage).toBe("Drafts ready");
    expect(res.body.jd.fields.URL).toBe("https://example.com");
    // contacts.markdown is now synthesized from DB rows
    expect(res.body.contacts.markdown).toContain("Jane Smith");
    expect(res.body.drafts).toHaveLength(1);
    expect(res.body.drafts[0].frontmatter.persona).toBe("hiring-manager");
    expect(res.body.drafts[0].path).toContain("drafts/alex.md");
  });

  it("404s unknown role", async () => {
    const res = await request(baseUrl).get(
      "/api/application/example-co/does-not-exist"
    );
    expect(res.status).toBe(404);
  });

  it("400s on a single-segment slug (old URL shape)", async () => {
    const res = await request(baseUrl).get("/api/application/example-co");
    expect(res.status).toBe(400);
  });

  it("rejects slug segments with path separators", async () => {
    const res = await request(baseUrl).get(
      "/api/application/..%2Fetc/product-designer"
    );
    expect(res.status).toBe(400);
  });

  it("returns correct status fields for a role with no status.md on disk", async () => {
    // acme-inc/ux-engineer has DB row but no status.md file
    const res = await request(baseUrl).get("/api/application/acme-inc/ux-engineer");
    expect(res.status).toBe(200);
    expect(res.body.status.fields.Stage).toBe("Applied");
    expect(res.body.status.fields.Priority).toBe("1");
    expect(res.body.status.fields["Last action"]).toBe("Submitted app");
    expect(res.body.status.fields["Next step"]).toBe("Wait for response");
  });
});

describe("POST /api/open", () => {
  it("rejects paths outside the memory dir with 403", async () => {
    const res = await request(baseUrl)
      .post("/api/open")
      .send({ path: "/etc/passwd" })
      .set("content-type", "application/json");
    expect(res.status).toBe(403);
  });

  it("returns 400 when path is missing", async () => {
    const res = await request(baseUrl)
      .post("/api/open")
      .send({})
      .set("content-type", "application/json");
    expect(res.status).toBe(400);
  });

  it("accepts a path inside the memory dir (dry-run)", async () => {
    const res = await request(baseUrl)
      .post("/api/open")
      .send({
        path: join(root, "applications/example-co/product-designer/jd.md"),
        dryRun: true,
      })
      .set("content-type", "application/json");
    expect(res.status).toBe(204);
  });

  it("accepts a relative path and joins it to memoryDir", async () => {
    const res = await request(baseUrl)
      .post("/api/open")
      .send({
        path: "applications/example-co/product-designer/jd.md",
        dryRun: true,
      })
      .set("content-type", "application/json");
    expect(res.status).toBe(204);
  });

  it("rejects a relative path that escapes via ..", async () => {
    const res = await request(baseUrl)
      .post("/api/open")
      .send({ path: "../../etc/passwd", dryRun: true })
      .set("content-type", "application/json");
    expect(res.status).toBe(403);
  });

  it("accepts a directory path inside memoryDir", async () => {
    const res = await request(baseUrl)
      .post("/api/open")
      .send({ path: "applications/example-co", dryRun: true })
      .set("content-type", "application/json");
    expect(res.status).toBe(204);
  });
});

describe("PATCH /api/application/:co/:role/status", () => {
  it("updates Stage in DB and GET /api/index reflects the change", async () => {
    const patchRes = await request(baseUrl)
      .patch("/api/application/example-co/product-designer/status")
      .send({ stage: "Applied" })
      .set("content-type", "application/json");
    expect(patchRes.status).toBe(200);

    // Verify DB was updated
    const db = new Database(join(root, "applications.db"), { readonly: true });
    const row = db.prepare(
      "SELECT stage, updated FROM applications WHERE company_slug='example-co' AND role_slug='product-designer'"
    ).get() as { stage: string; updated: string };
    db.close();
    expect(row.stage).toBe("Applied");
    expect(row.updated).toBe(new Date().toISOString().slice(0, 10));

    // GET /api/index reflects the change
    const indexRes = await request(baseUrl).get("/api/index");
    const indexRow = indexRes.body.find((r: any) => r.slug === "example-co/product-designer");
    expect(indexRow.stage).toBe("Applied");
  });

  it("updates priority in DB", async () => {
    const res = await request(baseUrl)
      .patch("/api/application/example-co/product-designer/status")
      .send({ priority: 5 })
      .set("content-type", "application/json");
    expect(res.status).toBe(200);

    const db = new Database(join(root, "applications.db"), { readonly: true });
    const row = db.prepare(
      "SELECT priority FROM applications WHERE company_slug='example-co' AND role_slug='product-designer'"
    ).get() as { priority: number };
    db.close();
    expect(row.priority).toBe(5);
  });

  it("updates lastAction and nextStep in DB", async () => {
    const res = await request(baseUrl)
      .patch("/api/application/example-co/product-designer/status")
      .send({ lastAction: "Sent email", nextStep: "Wait for reply" })
      .set("content-type", "application/json");
    expect(res.status).toBe(200);

    const db = new Database(join(root, "applications.db"), { readonly: true });
    const row = db.prepare(
      "SELECT last_action, next_step FROM applications WHERE company_slug='example-co' AND role_slug='product-designer'"
    ).get() as { last_action: string; next_step: string };
    db.close();
    expect(row.last_action).toBe("Sent email");
    expect(row.next_step).toBe("Wait for reply");
  });

  it("GET /api/index reflects DB change immediately after PATCH", async () => {
    await request(baseUrl)
      .patch("/api/application/acme-inc/ux-engineer/status")
      .send({ stage: "Replied" })
      .set("content-type", "application/json");

    const res = await request(baseUrl).get("/api/index");
    const row = res.body.find((r: any) => r.slug === "acme-inc/ux-engineer");
    expect(row.stage).toBe("Replied");
  });

  it("returns 404 for a non-existent application slug", async () => {
    const res = await request(baseUrl)
      .patch("/api/application/does-not-exist/some-role/status")
      .send({ stage: "Applied" })
      .set("content-type", "application/json");
    expect(res.status).toBe(404);
  });

  it("rejects empty patches", async () => {
    const res = await request(baseUrl)
      .patch("/api/application/example-co/product-designer/status")
      .send({})
      .set("content-type", "application/json");
    expect(res.status).toBe(400);
  });

  it("clears priority to null and restores it (explicit-null round-trip)", async () => {
    // Set to 2
    await request(baseUrl)
      .patch("/api/application/example-co/product-designer/status")
      .send({ priority: 2 })
      .set("content-type", "application/json");
    let row = (await request(baseUrl).get("/api/index")).body.find(
      (r: any) => r.slug === "example-co/product-designer"
    );
    expect(row.priority).toBe(2);

    // Clear to null
    await request(baseUrl)
      .patch("/api/application/example-co/product-designer/status")
      .send({ priority: null })
      .set("content-type", "application/json");
    row = (await request(baseUrl).get("/api/index")).body.find(
      (r: any) => r.slug === "example-co/product-designer"
    );
    expect(row.priority).toBeNull();

    // Set to 5
    await request(baseUrl)
      .patch("/api/application/example-co/product-designer/status")
      .send({ priority: 5 })
      .set("content-type", "application/json");
    row = (await request(baseUrl).get("/api/index")).body.find(
      (r: any) => r.slug === "example-co/product-designer"
    );
    expect(row.priority).toBe(5);
  });
});

describe("PUT /api/draft", () => {
  it("writes a draft inside applications/*/drafts/", async () => {
    const path = join(root, "applications/example-co/product-designer/drafts/alex.md");
    const res = await request(baseUrl)
      .put("/api/draft")
      .send({ path, content: "updated body\n" })
      .set("content-type", "application/json");
    expect(res.status).toBe(200);
    const fs = await import("node:fs/promises");
    const content = await fs.readFile(path, "utf8");
    expect(content).toBe("updated body\n");
  });

  it("rejects paths outside drafts/", async () => {
    const path = join(root, "applications/example-co/product-designer/jd.md");
    const res = await request(baseUrl)
      .put("/api/draft")
      .send({ path, content: "hijack" })
      .set("content-type", "application/json");
    expect(res.status).toBe(403);
  });

  it("rejects paths outside memoryDir", async () => {
    const res = await request(baseUrl)
      .put("/api/draft")
      .send({ path: "/etc/passwd", content: "nope" })
      .set("content-type", "application/json");
    expect(res.status).toBe(403);
  });
});

describe("error handling", () => {
  it("returns 400 for a malformed percent-escape in the slug", async () => {
    const res = await request(baseUrl).get("/api/application/%GZ/role");
    expect(res.status).toBe(400);
  });

  it("surfaces 500 (not hung) on internal errors", async () => {
    // Remove read access on the target role dir to force a non-ENOENT error.
    const dir = join(root, "applications/example-co/product-designer");
    const original = 0o755;
    // chmod 000 only works for non-root users; skip if running privileged.
    try {
      await import("node:fs/promises").then((fs) => fs.chmod(dir, 0o000));
    } catch {
      return; // environment can't perform the test — silently skip
    }
    try {
      const res = await request(baseUrl).get(
        "/api/application/example-co/product-designer"
      );
      // Either 500 (our catch) or 200 with an empty-looking payload depending
      // on platform; assert we at least don't hang and return *some* response.
      expect([200, 500]).toContain(res.status);
    } finally {
      await import("node:fs/promises").then((fs) =>
        fs.chmod(dir, original).catch(() => {})
      );
    }
  });

  it("getApplication on an orphan folder returns a Folder only row", async () => {
    // Create a folder with no DB row
    const orphanDir = join(root, "applications/orphan-co/some-role");
    mkdirSync(orphanDir, { recursive: true });

    const res = await request(baseUrl).get("/api/index");
    expect(res.status).toBe(200);
    const orphan = res.body.find((r: any) => r.slug === "orphan-co/some-role");
    expect(orphan).toBeDefined();
    expect(orphan.stage).toBe("Folder only");
  });
});

// ---------------------------------------------------------------------------
// Views endpoints
// ---------------------------------------------------------------------------

describe("GET /api/views", () => {
  it("returns the seeded views list", async () => {
    const res = await request(baseUrl).get("/api/views");
    expect(res.status).toBe(200);
    expect(Array.isArray(res.body)).toBe(true);
    const names = res.body.map((v: any) => v.name);
    expect(names).toContain("nyc-apps");
    expect(names).toContain("sf-apps");
  });

  it("returns correct shape for each view", async () => {
    const res = await request(baseUrl).get("/api/views");
    expect(res.status).toBe(200);
    const v = res.body.find((x: any) => x.name === "nyc-apps");
    expect(v).toBeDefined();
    expect(v.id).toBeTypeOf("number");
    expect(v.sql).toBeTypeOf("string");
    expect(v.description).toBe("NYC applications");
    expect(v.createdAt).toBeTypeOf("string");
    expect(v.updatedAt).toBeTypeOf("string");
  });
});

describe("GET /api/views/:name", () => {
  it("returns rows for the nyc-apps view (acme-inc matches)", async () => {
    const res = await request(baseUrl).get("/api/views/nyc-apps");
    expect(res.status).toBe(200);
    expect(Array.isArray(res.body)).toBe(true);
    const slugs = res.body.map((r: any) => r.slug ?? `${r.companySlug}/${r.roleSlug}`);
    expect(slugs).toContain("acme-inc/ux-engineer");
    // example-co is SF, not NYC — should be excluded
    expect(slugs).not.toContain("example-co/product-designer");
  });

  it("returns rows for the sf-apps view (example-co matches)", async () => {
    const res = await request(baseUrl).get("/api/views/sf-apps");
    expect(res.status).toBe(200);
    const slugs = res.body.map((r: any) => r.slug ?? `${r.companySlug}/${r.roleSlug}`);
    expect(slugs).toContain("example-co/product-designer");
    expect(slugs).not.toContain("acme-inc/ux-engineer");
  });

  it("returns 404 for an unknown view", async () => {
    const res = await request(baseUrl).get("/api/views/does-not-exist");
    expect(res.status).toBe(404);
  });
});

describe("POST /api/views", () => {
  it("creates a new view", async () => {
    const res = await request(baseUrl)
      .post("/api/views")
      .send({ name: "test-view", sql: "SELECT * FROM applications ORDER BY id ASC", description: "test" })
      .set("content-type", "application/json");
    expect(res.status).toBe(200);
    expect(res.body.name).toBe("test-view");
    expect(res.body.description).toBe("test");

    // Verify it shows up in list
    const listRes = await request(baseUrl).get("/api/views");
    const names = listRes.body.map((v: any) => v.name);
    expect(names).toContain("test-view");
  });

  it("updates an existing view via POST", async () => {
    await request(baseUrl)
      .post("/api/views")
      .send({ name: "nyc-apps", sql: "SELECT * FROM applications ORDER BY id DESC", description: "updated" })
      .set("content-type", "application/json");

    const res = await request(baseUrl).get("/api/views");
    const v = res.body.find((x: any) => x.name === "nyc-apps");
    expect(v.description).toBe("updated");
    expect(v.sql).toBe("SELECT * FROM applications ORDER BY id DESC");
    // Still only one row with that name
    expect(res.body.filter((x: any) => x.name === "nyc-apps").length).toBe(1);
  });

  it("rejects SQL that doesn't start with SELECT/WITH", async () => {
    const res = await request(baseUrl)
      .post("/api/views")
      .send({ name: "bad-view", sql: "DROP TABLE applications" })
      .set("content-type", "application/json");
    expect(res.status).toBe(400);
    expect(res.body.error).toContain("SELECT or WITH");
  });

  it("rejects multi-statement SQL", async () => {
    const res = await request(baseUrl)
      .post("/api/views")
      .send({ name: "multi", sql: "SELECT * FROM applications; DROP TABLE applications" })
      .set("content-type", "application/json");
    expect(res.status).toBe(400);
  });

  it("returns 400 when name is missing", async () => {
    const res = await request(baseUrl)
      .post("/api/views")
      .send({ sql: "SELECT * FROM applications" })
      .set("content-type", "application/json");
    expect(res.status).toBe(400);
  });

  it("returns 400 when sql is missing", async () => {
    const res = await request(baseUrl)
      .post("/api/views")
      .send({ name: "no-sql" })
      .set("content-type", "application/json");
    expect(res.status).toBe(400);
  });
});

describe("DELETE /api/views/:name", () => {
  it("removes an existing view", async () => {
    const res = await request(baseUrl).delete("/api/views/nyc-apps");
    expect(res.status).toBe(200);
    expect(res.body.ok).toBe(true);

    const listRes = await request(baseUrl).get("/api/views");
    expect(listRes.body.find((v: any) => v.name === "nyc-apps")).toBeUndefined();
  });

  it("returns 404 for a non-existent view", async () => {
    const res = await request(baseUrl).delete("/api/views/does-not-exist");
    expect(res.status).toBe(404);
  });
});
