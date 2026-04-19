import { IncomingMessage, ServerResponse } from "node:http";
import { readFile, readdir, stat } from "node:fs/promises";
import { join, resolve, basename } from "node:path";
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
  try {
    const entries = await readdir(dir);
    const drafts = [];
    for (const name of entries) {
      if (!name.endsWith(".md")) continue;
      const raw = await readFile(join(dir, name), "utf8");
      const parsed = parseDraft(raw);
      drafts.push({ name, ...parsed });
    }
    return drafts.sort((a, b) => a.name.localeCompare(b.name));
  } catch {
    return [];
  }
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
    const raw = await readIfExists(join(memoryDir, "applications/index.md"));
    json(res, 200, raw ? parseIndex(raw) : []);
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
    if (!isInside(memoryDir, body.path)) {
      return json(res, 403, { error: "path outside memory dir" });
    }
    if (body.dryRun) {
      res.statusCode = 204;
      return res.end();
    }
    launchEditor(body.path);
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
    try {
      if (req.method === "GET" && p === "/api/index") return void getIndex(res);
      if (req.method === "GET" && p.startsWith("/api/application/")) {
        const slug = decodeURIComponent(p.slice("/api/application/".length));
        return void getApplication(res, slug);
      }
      if (req.method === "POST" && p === "/api/open") {
        return void postOpen(req, res);
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
