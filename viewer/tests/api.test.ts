import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync, writeFileSync, mkdirSync, realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import http from "node:http";
import request from "supertest";
import { createApi } from "../server/api";

let root: string;
let server: http.Server;
let baseUrl: string;

function seed(root: string) {
  mkdirSync(join(root, "applications/example-co/drafts"), { recursive: true });
  writeFileSync(
    join(root, "applications/index.md"),
    "| Company | Role | Stage | Last action | Next | Updated |\n" +
      "|---|---|---|---|---|---|\n" +
      "| Example Co | Product Designer | Drafts ready | V1 picked | Send | 2026-04-19 |\n"
  );
  writeFileSync(
    join(root, "applications/example-co/status.md"),
    "# Example Co\n\n- **Stage:** Drafts ready\n"
  );
  writeFileSync(
    join(root, "applications/example-co/jd.md"),
    "# Example Co\n\n- **URL:** https://example.com\n\n## Role\n\nbody\n"
  );
  writeFileSync(
    join(root, "applications/example-co/contacts.md"),
    "# Example Co\n\nnotes\n"
  );
  writeFileSync(
    join(root, "applications/example-co/drafts/alex.md"),
    "---\npersona: hiring-manager\n---\nBody here.\n"
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
  server = http.createServer(api.handler);
  await new Promise<void>((r) => server.listen(0, r));
  const addr = server.address();
  if (!addr || typeof addr === "string") throw new Error("no addr");
  baseUrl = `http://127.0.0.1:${addr.port}`;
});

afterEach(async () => {
  await new Promise<void>((r) => server.close(() => r()));
  rmSync(root, { recursive: true, force: true });
});

describe("GET /api/index", () => {
  it("returns parsed index rows", async () => {
    const res = await request(baseUrl).get("/api/index");
    expect(res.status).toBe(200);
    expect(res.body).toHaveLength(1);
    expect(res.body[0].company).toBe("Example Co");
  });
});

describe("GET /api/application/:slug", () => {
  it("returns the full application payload", async () => {
    const res = await request(baseUrl).get("/api/application/example-co");
    expect(res.status).toBe(200);
    expect(res.body.slug).toBe("example-co");
    expect(res.body.status.fields.Stage).toBe("Drafts ready");
    expect(res.body.jd.fields.URL).toBe("https://example.com");
    expect(res.body.contacts.markdown).toContain("notes");
    expect(res.body.drafts).toHaveLength(1);
    expect(res.body.drafts[0].frontmatter.persona).toBe("hiring-manager");
  });

  it("404s unknown slug", async () => {
    const res = await request(baseUrl).get("/api/application/unknown");
    expect(res.status).toBe(404);
  });

  it("rejects slugs with path separators", async () => {
    const res = await request(baseUrl).get("/api/application/..%2Fetc");
    expect(res.status).toBe(400);
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
      .send({ path: join(root, "applications/example-co/status.md"), dryRun: true })
      .set("content-type", "application/json");
    expect(res.status).toBe(204);
  });
});
