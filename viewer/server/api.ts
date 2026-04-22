import { IncomingMessage, ServerResponse } from "node:http";
import { readFile, readdir, stat, writeFile } from "node:fs/promises";
import { join, resolve, isAbsolute, sep } from "node:path";
import { spawn } from "node:child_process";
import { parseJd, parseDraft } from "../src/lib/parsers";
import { isInside } from "./safePath";
import type { Watcher, MemoryEvent } from "./watcher";
import { openDb, dbPathFor, getIndex as dbGetIndex, getApplication as dbGetApplication, patchStatus as dbPatchStatus, NoSuchApplicationError } from "./db";
import {
  listViews as dbListViews,
  runView as dbRunView,
  createOrUpdateView as dbCreateOrUpdateView,
  deleteView as dbDeleteView,
  closeReadOnlyHandles,
  ViewSqlError,
} from "./views";

export interface ApiOptions {
  memoryDir: string;
  watcher: Watcher | null;
}

export interface Api {
  handler: (req: IncomingMessage, res: ServerResponse) => void;
  close: () => void;
}

const segmentRegex = /^[a-z0-9][a-z0-9-_]*$/i;

function json(res: ServerResponse, status: number, body: unknown) {
  res.statusCode = status;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.end(JSON.stringify(body));
}

function text(res: ServerResponse, status: number, body: string) {
  res.statusCode = status;
  res.setHeader("content-type", "text/plain; charset=utf-8");
  res.end(body);
}

async function readBody(req: IncomingMessage): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const c of req) chunks.push(c as Buffer);
  return Buffer.concat(chunks).toString("utf8");
}

async function readIfExists(path: string): Promise<string | null> {
  try {
    return await readFile(path, "utf8");
  } catch {
    return null;
  }
}

async function listDrafts(dir: string) {
  let entries: string[];
  try {
    entries = await readdir(dir);
  } catch {
    return [];
  }
  const drafts = [];
  for (const name of entries) {
    if (!name.endsWith(".md")) continue;
    try {
      const raw = await readFile(join(dir, name), "utf8");
      drafts.push({ name, path: join(dir, name), raw, ...parseDraft(raw) });
    } catch (err) {
      console.warn(`skipping draft ${name}:`, err);
    }
  }
  return drafts.sort((a, b) => a.name.localeCompare(b.name));
}

// Editor fallback chain, per spec:
//   $EDITOR → `code` → `open` (macOS) / `xdg-open` (Linux).
// Spawns detached with an argv array — never uses a shell.
function launchEditor(target: string) {
  const fallback =
    process.platform === "darwin"
      ? "open"
      : process.platform === "linux"
        ? "xdg-open"
        : "code";
  const candidates = [process.env.EDITOR, "code", fallback].filter(
    (c): c is string => !!c
  );
  tryLaunch(candidates, target);
}

function tryLaunch(cmds: string[], target: string) {
  if (cmds.length === 0) return;
  const [head, ...rest] = cmds;
  const child = spawn(head, [target], { detached: true, stdio: "ignore" });
  child.on("error", () => tryLaunch(rest, target));
  child.unref();
}

export function createApi(opts: ApiOptions): Api {
  const memoryDir = resolve(opts.memoryDir);
  const watcher = opts.watcher;

  // Open DB once. Throws clearly if the DB doesn't exist (run the migration first).
  const db = openDb(memoryDir);
  const dbPath = dbPathFor(memoryDir);

  // Close DB on process exit to flush WAL.
  const teardown = () => {
    try { db.close(); } catch { /* ignore */ }
    closeReadOnlyHandles();
    process.off("exit", teardown);
    process.off("SIGINT", sigintHandler);
    process.off("SIGTERM", sigtermHandler);
  };
  const sigintHandler = () => { teardown(); process.exit(0); };
  const sigtermHandler = () => { teardown(); process.exit(0); };
  process.once("exit", teardown);
  process.once("SIGINT", sigintHandler);
  process.once("SIGTERM", sigtermHandler);

  // ---------------------------------------------------------------------------
  // Helpers for orphan-folder location (still from jd.md on disk)
  // ---------------------------------------------------------------------------

  async function locationFromJd(companySlug: string, roleSlug: string): Promise<string> {
    const jdPath = join(memoryDir, "applications", companySlug, roleSlug, "jd.md");
    const raw = await readIfExists(jdPath);
    if (!raw) return "";
    for (const line of raw.split("\n")) {
      const m = line.match(/^\s*(?:[-*]\s+)?\*\*Location:\*\*\s*(.+)$/);
      if (m) return m[1].trim();
    }
    return "";
  }

  // ---------------------------------------------------------------------------
  // Synthesize a contacts.markdown string from structured DB rows.
  // Groups by tier, renders each contact as ### Name + bullets.
  // ---------------------------------------------------------------------------

  function synthesizeContactsMarkdown(
    contacts: Array<{
      name: string;
      role: string | null;
      linkedin: string | null;
      email: string | null;
      tier: string | null;
      notes: string | null;
    }>
  ): string {
    if (contacts.length === 0) return "";

    const byTier = new Map<string, typeof contacts>();
    for (const c of contacts) {
      const tier = c.tier ?? "other";
      if (!byTier.has(tier)) byTier.set(tier, []);
      byTier.get(tier)!.push(c);
    }

    const tierOrder = ["warm", "semi-warm", "cold", "other"];
    const sections: string[] = [];
    for (const tier of tierOrder) {
      const list = byTier.get(tier);
      if (!list) continue;
      sections.push(`## ${tier.charAt(0).toUpperCase()}${tier.slice(1)}`);
      for (const c of list) {
        sections.push(`### ${c.name}`);
        if (c.role) sections.push(`- **Role:** ${c.role}`);
        if (c.linkedin) sections.push(`- **LinkedIn:** ${c.linkedin}`);
        if (c.email) sections.push(`- **Email:** ${c.email}`);
        if (c.notes) sections.push(`- **Notes:** ${c.notes}`);
      }
    }
    // Also handle any tiers not in the ordered list
    for (const [tier, list] of byTier) {
      if (tierOrder.includes(tier)) continue;
      sections.push(`## ${tier}`);
      for (const c of list) {
        sections.push(`### ${c.name}`);
        if (c.role) sections.push(`- **Role:** ${c.role}`);
        if (c.linkedin) sections.push(`- **LinkedIn:** ${c.linkedin}`);
        if (c.email) sections.push(`- **Email:** ${c.email}`);
        if (c.notes) sections.push(`- **Notes:** ${c.notes}`);
      }
    }
    return sections.join("\n\n");
  }

  // ---------------------------------------------------------------------------
  // GET /api/index — reads from DB, orphan folders still detected from disk.
  // ---------------------------------------------------------------------------

  async function getIndex(res: ServerResponse) {
    const dbRows = dbGetIndex(db);

    // Enumerate all role folders on disk to find orphans
    const appsDir = join(memoryDir, "applications");
    const roleFolders: Array<{ company: string; role: string }> = [];
    try {
      const companies = (await readdir(appsDir, { withFileTypes: true }))
        .filter((d) => d.isDirectory() && !d.name.startsWith("_") && !d.name.startsWith("."));
      for (const company of companies) {
        let inner: string[] = [];
        try {
          inner = (await readdir(join(appsDir, company.name), { withFileTypes: true }))
            .filter((d) => d.isDirectory() && !d.name.startsWith("_") && !d.name.startsWith("."))
            .map((d) => d.name);
        } catch {
          continue;
        }
        for (const role of inner) {
          roleFolders.push({ company: company.name, role });
        }
      }
    } catch {
      // no applications dir; nothing to surface
    }

    // DB is authoritative: dbRows already have location+priority. Find orphan folders
    // (folders on disk that have no DB row).
    const dbSlugs = new Set(dbRows.map((r) => r.slug));
    const orphans = await Promise.all(
      roleFolders
        .filter(({ company, role }) => !dbSlugs.has(`${company}/${role}`))
        .map(async ({ company, role }) => {
          const location = await locationFromJd(company, role);
          return {
            slug: `${company}/${role}`,
            companySlug: company,
            roleSlug: role,
            company,
            role: "(orphan folder)",
            stage: "Folder only",
            lastAction: "—",
            nextStep: "Add to index",
            updated: "",
            location,
            priority: null,
          };
        })
    );
    json(res, 200, [...dbRows, ...orphans]);
  }

  // ---------------------------------------------------------------------------
  // GET /api/application/:co/:role — reads structured fields from DB, body from disk.
  // ---------------------------------------------------------------------------

  async function getApplication(
    res: ServerResponse,
    companySlug: string,
    roleSlug: string
  ) {
    if (!segmentRegex.test(companySlug) || !segmentRegex.test(roleSlug)) {
      return json(res, 400, { error: "bad slug" });
    }
    const dir = join(memoryDir, "applications", companySlug, roleSlug);
    try {
      const s = await stat(dir);
      if (!s.isDirectory()) return json(res, 404, { error: "not found" });
    } catch {
      return json(res, 404, { error: "not found" });
    }

    const detail = dbGetApplication(db, companySlug, roleSlug);

    // Build status from DB columns — authoritative even when status.md is absent.
    const statusFields: Record<string, string> = {};
    if (detail) {
      const { app } = detail;
      statusFields["Stage"] = app.stage;
      if (app.priority !== null) statusFields["Priority"] = String(app.priority);
      if (app.lastAction && app.lastAction !== "—") statusFields["Last action"] = app.lastAction;
      if (app.nextStep) statusFields["Next step"] = app.nextStep;
    } else {
      // Folder exists on disk but not in DB — return minimal status
      statusFields["Stage"] = "Folder only";
    }

    const statusMarkdown = detail?.app.notes ?? "";

    // JD: fields from DB + body from disk
    let jdResponse: { fields: Record<string, string>; markdown: string } = {
      fields: {},
      markdown: "",
    };
    if (detail?.jd) {
      const { jd } = detail;
      const fields: Record<string, string> = {};
      if (jd.url) fields["URL"] = jd.url;
      if (jd.location) fields["Location"] = jd.location;
      if (jd.employment) fields["Employment"] = jd.employment;
      if (jd.compensationRaw) fields["Compensation"] = jd.compensationRaw;
      if (jd.fetchedAt) fields["Fetched"] = jd.fetchedAt;

      // Read body from disk path if available, otherwise fall back to jd.md in dir
      const jdMd = await readIfExists(jd.bodyPath ?? join(dir, "jd.md"));
      const parsedJd = jdMd ? parseJd(jdMd) : null;
      // Merge DB fields over parsed fields (DB is authoritative for structured data)
      jdResponse = {
        fields: { ...(parsedJd?.fields ?? {}), ...fields },
        markdown: jdMd ?? "",
      };
    } else {
      // No DB jd row — fall back to reading jd.md from disk
      const jdMd = await readIfExists(join(dir, "jd.md"));
      jdResponse = jdMd ? parseJd(jdMd) : { fields: {}, markdown: "" };
    }

    // Contacts: synthesize markdown from DB rows; fall back to contacts.md on disk
    let contactsMarkdown: string;
    if (detail && detail.contacts.length > 0) {
      contactsMarkdown = synthesizeContactsMarkdown(detail.contacts);
    } else {
      // No structured contacts in DB — try legacy contacts.md on disk
      contactsMarkdown = (await readIfExists(join(dir, "contacts.md"))) ?? "";
    }

    const drafts = await listDrafts(join(dir, "drafts"));

    json(res, 200, {
      slug: `${companySlug}/${roleSlug}`,
      companySlug,
      roleSlug,
      dir,
      status: { fields: statusFields, markdown: statusMarkdown },
      jd: jdResponse,
      contacts: { markdown: contactsMarkdown },
      drafts,
    });
  }

  async function patchStatus(
    req: IncomingMessage,
    res: ServerResponse,
    companySlug: string,
    roleSlug: string
  ) {
    if (!segmentRegex.test(companySlug) || !segmentRegex.test(roleSlug)) {
      return json(res, 400, { error: "bad slug" });
    }
    let body: {
      stage?: unknown;
      priority?: unknown;
      lastAction?: unknown;
      nextStep?: unknown;
    };
    try {
      body = JSON.parse(await readBody(req));
    } catch {
      return json(res, 400, { error: "invalid json" });
    }

    const patch: Parameters<typeof dbPatchStatus>[3] = {};
    if (typeof body.stage === "string") patch.stage = body.stage.trim();
    if (body.priority === null) patch.priority = null;
    else if (typeof body.priority === "number" && Number.isFinite(body.priority)) {
      patch.priority = Math.round(body.priority);
    } else if (typeof body.priority === "string") {
      const t = body.priority.trim();
      if (t === "") patch.priority = null;
      else {
        const n = parseInt(t, 10);
        if (!Number.isFinite(n)) return json(res, 400, { error: "invalid priority" });
        patch.priority = n;
      }
    }
    if (typeof body.lastAction === "string") patch.lastAction = body.lastAction.trim();
    if (typeof body.nextStep === "string") patch.nextStep = body.nextStep.trim();

    if (Object.keys(patch).length === 0) {
      return json(res, 400, { error: "no fields to update" });
    }

    try {
      dbPatchStatus(db, companySlug, roleSlug, patch);
    } catch (err) {
      if (err instanceof NoSuchApplicationError) {
        return json(res, 404, { error: "application not found" });
      }
      throw err;
    }

    json(res, 200, { ok: true });
  }

  async function putDraft(req: IncomingMessage, res: ServerResponse) {
    let body: { path?: unknown; content?: unknown };
    try {
      body = JSON.parse(await readBody(req));
    } catch {
      return json(res, 400, { error: "invalid json" });
    }
    if (typeof body.path !== "string" || typeof body.content !== "string") {
      return json(res, 400, { error: "path and content required" });
    }
    const target = isAbsolute(body.path) ? body.path : join(memoryDir, body.path);
    if (!isInside(memoryDir, target)) {
      return json(res, 403, { error: "path outside memory dir" });
    }
    // Drafts live at applications/<company>/<role>/drafts/<file>.md. Block
    // writes to any other shape so this endpoint can't rewrite status.md or jd.md.
    const relative = target.slice(resolve(memoryDir).length).split(sep).filter(Boolean);
    if (
      relative.length !== 5 ||
      relative[0] !== "applications" ||
      relative[3] !== "drafts" ||
      !/^[a-z0-9][a-z0-9._-]*\.md$/i.test(relative[4])
    ) {
      return json(res, 403, { error: "target must be applications/<co>/<role>/drafts/<name>.md" });
    }
    await writeFile(target, body.content, "utf8");
    json(res, 200, { ok: true });
  }

  async function postOpen(req: IncomingMessage, res: ServerResponse) {
    let body: { path?: string; dryRun?: boolean };
    try {
      body = JSON.parse(await readBody(req));
    } catch {
      return json(res, 400, { error: "invalid json" });
    }
    if (!body.path || typeof body.path !== "string") {
      return json(res, 400, { error: "path required" });
    }
    // Resolve: if absolute, keep as-is; if relative, join to memoryDir.
    const target = isAbsolute(body.path)
      ? body.path
      : join(memoryDir, body.path);
    if (!isInside(memoryDir, target)) {
      return json(res, 403, { error: "path outside memory dir" });
    }
    if (body.dryRun) {
      res.statusCode = 204;
      return res.end();
    }
    launchEditor(target);
    res.statusCode = 204;
    res.end();
  }

  async function postView(req: IncomingMessage, res: ServerResponse) {
    let body: { name?: unknown; sql?: unknown; description?: unknown };
    try {
      body = JSON.parse(await readBody(req));
    } catch {
      return json(res, 400, { error: "invalid json" });
    }
    if (typeof body.name !== "string" || !body.name.trim()) {
      return json(res, 400, { error: "name required" });
    }
    if (typeof body.sql !== "string" || !body.sql.trim()) {
      return json(res, 400, { error: "sql required" });
    }
    const description = typeof body.description === "string" ? body.description : undefined;
    try {
      const view = dbCreateOrUpdateView(db, body.name.trim(), body.sql.trim(), description);
      return json(res, 200, view);
    } catch (err) {
      if (err instanceof ViewSqlError) {
        return json(res, 400, { error: err.message });
      }
      throw err;
    }
  }

  function serveEvents(req: IncomingMessage, res: ServerResponse) {
    res.statusCode = 200;
    res.setHeader("content-type", "text/event-stream");
    res.setHeader("cache-control", "no-cache");
    res.setHeader("connection", "keep-alive");
    res.flushHeaders?.();
    const send = (ev: MemoryEvent) => {
      res.write(`data: ${JSON.stringify(ev)}\n\n`);
    };
    const unsubscribe = watcher?.on(send);
    const heartbeat = setInterval(() => res.write(`: ping\n\n`), 15000);
    req.on("close", () => {
      clearInterval(heartbeat);
      unsubscribe?.();
    });
  }

  function handler(req: IncomingMessage, res: ServerResponse) {
    const url = new URL(req.url || "/", "http://localhost");
    const p = url.pathname;

    const run = (promise: Promise<unknown>) =>
      promise.catch((err) => {
        console.error("api error", err);
        if (!res.headersSent) json(res, 500, { error: "internal error" });
        else res.end();
      });

    try {
      if (req.method === "GET" && p === "/api/index") {
        return void run(getIndex(res));
      }
      if (p.startsWith("/api/application/")) {
        const rest = p.slice("/api/application/".length);
        const parts = rest.split("/").filter(Boolean);
        let companySlug: string | undefined;
        let roleSlug: string | undefined;
        try {
          if (parts[0] !== undefined) companySlug = decodeURIComponent(parts[0]);
          if (parts[1] !== undefined) roleSlug = decodeURIComponent(parts[1]);
        } catch {
          return json(res, 400, { error: "bad slug" });
        }
        if (
          req.method === "PATCH" &&
          parts.length === 3 &&
          parts[2] === "status" &&
          companySlug &&
          roleSlug
        ) {
          return void run(patchStatus(req, res, companySlug, roleSlug));
        }
        if (req.method === "GET" && parts.length === 2 && companySlug && roleSlug) {
          return void run(getApplication(res, companySlug, roleSlug));
        }
        return json(res, 400, { error: "bad slug" });
      }
      if (req.method === "PUT" && p === "/api/draft") {
        return void run(putDraft(req, res));
      }
      if (req.method === "POST" && p === "/api/open") {
        return void run(postOpen(req, res));
      }
      if (req.method === "GET" && p === "/api/events") {
        return serveEvents(req, res);
      }

      // -----------------------------------------------------------------------
      // Views endpoints
      // -----------------------------------------------------------------------

      if (req.method === "GET" && p === "/api/views") {
        return json(res, 200, dbListViews(db));
      }

      if (p.startsWith("/api/views/")) {
        const rawName = p.slice("/api/views/".length);
        let viewName: string;
        try {
          viewName = decodeURIComponent(rawName);
        } catch {
          return json(res, 400, { error: "bad view name" });
        }
        if (!viewName) {
          return json(res, 400, { error: "view name required" });
        }

        if (req.method === "GET") {
          return void run(
            dbRunView(db, dbPath, viewName).then((rows) => {
              if (rows === null) {
                return json(res, 404, { error: "view not found" });
              }
              return json(res, 200, rows);
            }).catch((err) => {
              if (err instanceof ViewSqlError) {
                return json(res, 400, { error: err.message });
              }
              throw err;
            })
          );
        }

        if (req.method === "DELETE") {
          const deleted = dbDeleteView(db, viewName);
          if (!deleted) return json(res, 404, { error: "view not found" });
          return json(res, 200, { ok: true });
        }
      }

      if (req.method === "POST" && p === "/api/views") {
        return void run(postView(req, res));
      }

      text(res, 404, "not found");
    } catch (err) {
      console.error("api error", err);
      json(res, 500, { error: "internal error" });
    }
  }

  return { handler, close: teardown };
}
