import Database from "better-sqlite3";
import { Worker } from "node:worker_threads";
import type { IndexRow } from "./db";

// ---------------------------------------------------------------------------
// Worker script (plain JS, embedded as a string — runs in a separate thread
// so we can enforce a hard wall-clock timeout via worker.terminate()).
// ---------------------------------------------------------------------------

const WORKER_SCRIPT = `
const { workerData, parentPort } = require('node:worker_threads');
const Database = require('better-sqlite3');
const { dbPath, sql } = workerData;
try {
  const db = new Database(dbPath, { readonly: true, fileMustExist: true });
  db.pragma('busy_timeout = 5000');
  const rows = db.prepare(sql).all();
  db.close();
  parentPort.postMessage({ ok: true, rows });
} catch (err) {
  parentPort.postMessage({ ok: false, message: err.message });
}
`;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ViewRow {
  id: number;
  name: string;
  sql: string;
  description: string | null;
  createdAt: string;
  updatedAt: string;
}

// ---------------------------------------------------------------------------
// SQL validator
// ---------------------------------------------------------------------------

export class ViewSqlError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ViewSqlError";
  }
}

/**
 * Single-pass state machine that strips SQL comments and string literals,
 * returning a sanitised string suitable for structural validation.
 *
 * Handles:
 *  - `--` line comments
 *  - `/* … *\/` block comments (non-nesting, per SQLite spec)
 *  - Single-quoted string literals with SQL-style `''` escape
 *  - Unterminated block comments → treated as malformed (returns sentinel)
 */
function stripForValidation(sql: string): string {
  let out = "";
  let i = 0;
  while (i < sql.length) {
    const c = sql[i];
    const next = sql[i + 1];

    // Line comment: consume until newline (or EOF).
    if (c === "-" && next === "-") {
      while (i < sql.length && sql[i] !== "\n") i++;
      continue;
    }

    // Block comment: consume until closing */. Unterminated → return sentinel.
    if (c === "/" && next === "*") {
      i += 2;
      let closed = false;
      while (i < sql.length - 1) {
        if (sql[i] === "*" && sql[i + 1] === "/") {
          i += 2;
          closed = true;
          break;
        }
        i++;
      }
      if (!closed) {
        // Unterminated block comment — signal by injecting a `;` so the caller
        // rejects the statement as malformed/multi-statement.
        return out + ";__unterminated_block_comment__";
      }
      continue;
    }

    // Single-quoted string literal with SQL-style '' escape.
    if (c === "'") {
      out += "''"; // emit placeholder; length accuracy is unimportant
      i++;
      while (i < sql.length) {
        if (sql[i] === "'" && sql[i + 1] === "'") { i += 2; continue; }
        if (sql[i] === "'") { i++; break; }
        i++;
      }
      continue;
    }

    out += c;
    i++;
  }
  return out;
}

/**
 * Validate that `sql` is a single read-only SELECT or WITH statement.
 *
 * Rules (checked after single-pass comment/string stripping):
 *  1. Stripped text must start with SELECT or WITH.
 *  2. A trailing semicolon is allowed; any semicolon before end-of-text is not.
 */
export function validateViewSql(sql: string): void {
  const stripped = stripForValidation(sql).trim().replace(/;\s*$/, "");

  if (!/^(select|with)\b/i.test(stripped)) {
    throw new ViewSqlError(
      "View SQL must start with SELECT or WITH (after stripping comments)"
    );
  }

  if (stripped.includes(";")) {
    throw new ViewSqlError(
      "View SQL must be a single statement (no unquoted semicolons)"
    );
  }
}

// ---------------------------------------------------------------------------
// Teardown hook (kept for API compatibility — workers open their own handles)
// ---------------------------------------------------------------------------

/**
 * No-op: previously closed cached read-only handles; query execution now
 * runs in worker threads that manage their own DB handles.
 */
export function closeReadOnlyHandles(): void {
  // nothing to close — workers open and close their own connections
}

// ---------------------------------------------------------------------------
// Map a raw DB row (snake_case, arbitrary columns) → IndexRow
// ---------------------------------------------------------------------------

function toIndexRow(raw: Record<string, unknown>): IndexRow {
  return {
    id: (raw["id"] as number | null) ?? 0,
    slug: raw["slug"] as string | undefined
      ?? `${raw["company_slug"] ?? ""}/${raw["role_slug"] ?? ""}`,
    companySlug: (raw["company_slug"] as string | null) ?? "",
    roleSlug: (raw["role_slug"] as string | null) ?? "",
    company: (raw["company"] as string | null) ?? "",
    role: (raw["role"] as string | null) ?? "",
    stage: (raw["stage"] as string | null) ?? "",
    priority: (raw["priority"] as number | null) ?? null,
    lastAction: (raw["last_action"] as string | null) ?? "—",
    nextStep: (raw["next_step"] as string | null) ?? "",
    updated: (raw["updated"] as string | null) ?? "",
    createdAt: (raw["created_at"] as string | null) ?? "",
    notes: (raw["notes"] as string | null) ?? null,
    location: (raw["location"] as string | null) ?? null,
  };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function listViews(db: Database.Database): ViewRow[] {
  const rows = db
    .prepare("SELECT id, name, sql, description, created_at, updated_at FROM views ORDER BY name ASC")
    .all() as Record<string, unknown>[];

  return rows.map((r) => ({
    id: r["id"] as number,
    name: r["name"] as string,
    sql: r["sql"] as string,
    description: (r["description"] as string | null) ?? null,
    createdAt: r["created_at"] as string,
    updatedAt: r["updated_at"] as string,
  }));
}

export async function runView(
  db: Database.Database,
  dbPath: string,
  name: string
): Promise<IndexRow[] | null> {
  const viewRow = db
    .prepare("SELECT sql FROM views WHERE name = ?")
    .get(name) as { sql: string } | undefined;

  if (!viewRow) {
    return null;
  }

  // Validate before executing — belt-and-suspenders even for stored SQL.
  validateViewSql(viewRow.sql);

  // Run the query in a worker thread so we can enforce a hard wall-clock
  // timeout via worker.terminate() — better-sqlite3 is synchronous and
  // provides no interrupt API, so a separate thread is the only safe option.
  return new Promise<IndexRow[] | null>((resolve, reject) => {
    let settled = false;
    let timeoutHandle: ReturnType<typeof setTimeout> | undefined;

    const settle = (fn: () => void) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeoutHandle);
      fn();
    };

    const worker = new Worker(WORKER_SCRIPT, {
      eval: true,
      workerData: { dbPath, sql: viewRow.sql },
    });

    timeoutHandle = setTimeout(() => {
      worker.terminate().catch(() => {/* ignore */});
      settle(() => reject(new ViewSqlError("View query exceeded 500ms")));
    }, 500);

    worker.on("message", (msg: { ok: boolean; rows?: Record<string, unknown>[]; message?: string }) => {
      settle(() => {
        if (msg.ok) {
          resolve((msg.rows ?? []).map(toIndexRow));
        } else {
          reject(new Error(msg.message ?? "Query failed"));
        }
      });
    });

    worker.on("error", (err) => {
      settle(() => reject(err));
    });

    worker.on("exit", (code) => {
      if (code !== 0) {
        settle(() => reject(new Error(`Worker exited with code ${code}`)));
      }
    });
  });
}

export function createOrUpdateView(
  db: Database.Database,
  name: string,
  sql: string,
  description?: string
): ViewRow {
  validateViewSql(sql);
  const now = new Date().toISOString().slice(0, 19) + "Z";

  const existing = db
    .prepare("SELECT id FROM views WHERE name = ?")
    .get(name) as { id: number } | undefined;

  if (existing) {
    db.prepare(
      "UPDATE views SET sql = ?, description = ?, updated_at = ? WHERE name = ?"
    ).run(sql, description ?? null, now, name);
  } else {
    db.prepare(
      "INSERT INTO views (name, sql, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)"
    ).run(name, sql, description ?? null, now, now);
  }

  const row = db
    .prepare("SELECT id, name, sql, description, created_at, updated_at FROM views WHERE name = ?")
    .get(name) as Record<string, unknown>;

  return {
    id: row["id"] as number,
    name: row["name"] as string,
    sql: row["sql"] as string,
    description: (row["description"] as string | null) ?? null,
    createdAt: row["created_at"] as string,
    updatedAt: row["updated_at"] as string,
  };
}

export function deleteView(db: Database.Database, name: string): boolean {
  const result = db.prepare("DELETE FROM views WHERE name = ?").run(name);
  return result.changes > 0;
}
