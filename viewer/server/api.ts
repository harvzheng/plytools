import { IncomingMessage, ServerResponse } from "node:http";
import { readFile, readdir, stat } from "node:fs/promises";
import { join, resolve, isAbsolute } from "node:path";
import { spawn } from "node:child_process";
import { parseIndex, parseStatus, parseJd, parseDraft } from "../src/lib/parsers";
import { isInside } from "./safePath";
import type { Watcher, MemoryEvent } from "./watcher";

export interface ApiOptions {
  memoryDir: string;
  watcher: Watcher | null;
}

export interface Api {
  handler: (req: IncomingMessage, res: ServerResponse) => void;
}

const slugRegex = /^[a-z0-9][a-z0-9-_]*$/i;

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
      drafts.push({ name, path: join(dir, name), ...parseDraft(raw) });
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

  async function getIndex(res: ServerResponse) {
    const indexPath = join(memoryDir, "applications/index.md");
    const raw = await readIfExists(indexPath);
    const indexRows = raw ? parseIndex(raw) : [];

    const appsDir = join(memoryDir, "applications");
    let folders: string[] = [];
    try {
      folders = (await readdir(appsDir, { withFileTypes: true }))
        .filter((d) => d.isDirectory() && !d.name.startsWith("_") && !d.name.startsWith("."))
        .map((d) => d.name);
    } catch {
      // no applications dir; nothing to surface
    }

    const indexedSlugs = new Set(indexRows.map((r) => r.slug));
    const orphans = folders
      .filter((name) => !indexedSlugs.has(name))
      .map((name) => ({
        slug: name,
        company: name,
        role: "(orphan folder)",
        stage: "Folder only",
        lastAction: "—",
        nextStep: "Add to index.md",
        updated: "",
      }));

    json(res, 200, [...indexRows, ...orphans]);
  }

  async function getApplication(res: ServerResponse, slug: string) {
    if (!slugRegex.test(slug)) return json(res, 400, { error: "bad slug" });
    const dir = join(memoryDir, "applications", slug);
    try {
      const s = await stat(dir);
      if (!s.isDirectory()) return json(res, 404, { error: "not found" });
    } catch {
      return json(res, 404, { error: "not found" });
    }
    const [statusMd, jdMd, contactsMd, drafts] = await Promise.all([
      readIfExists(join(dir, "status.md")),
      readIfExists(join(dir, "jd.md")),
      readIfExists(join(dir, "contacts.md")),
      listDrafts(join(dir, "drafts")),
    ]);
    json(res, 200, {
      slug,
      dir,
      status: statusMd ? parseStatus(statusMd) : { fields: {}, markdown: "" },
      jd: jdMd ? parseJd(jdMd) : { fields: {}, markdown: "" },
      contacts: { markdown: contactsMd ?? "" },
      drafts,
    });
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
      if (req.method === "GET" && p.startsWith("/api/application/")) {
        let slug: string;
        try {
          slug = decodeURIComponent(p.slice("/api/application/".length));
        } catch {
          return json(res, 400, { error: "bad slug" });
        }
        return void run(getApplication(res, slug));
      }
      if (req.method === "POST" && p === "/api/open") {
        return void run(postOpen(req, res));
      }
      if (req.method === "GET" && p === "/api/events") {
        return serveEvents(req, res);
      }
      text(res, 404, "not found");
    } catch (err) {
      console.error("api error", err);
      json(res, 500, { error: "internal error" });
    }
  }

  return { handler };
}
