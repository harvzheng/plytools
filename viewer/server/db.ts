import Database from "better-sqlite3";
import { join } from "node:path";
import { existsSync } from "node:fs";

// ---------------------------------------------------------------------------
// Typed errors
// ---------------------------------------------------------------------------

export class NoSuchApplicationError extends Error {
  constructor(public slug: string) {
    super(`No application row found for ${slug}`);
    this.name = "NoSuchApplicationError";
  }
}

// ---------------------------------------------------------------------------
// Types — mirror the camelCase shapes the HTTP clients already expect.
// ---------------------------------------------------------------------------

export interface IndexRow {
  id: number;
  slug: string;
  companySlug: string;
  roleSlug: string;
  company: string;
  role: string;
  stage: string;
  priority: number | null;
  lastAction: string;
  nextStep: string;
  updated: string;
  createdAt: string;
  notes: string | null;
  // jd join
  location: string | null;
}

export interface AppRow {
  id: number;
  slug: string;
  companySlug: string;
  roleSlug: string;
  company: string;
  role: string;
  stage: string;
  priority: number | null;
  lastAction: string;
  nextStep: string;
  updated: string;
  createdAt: string;
  notes: string | null;
}

export interface JdRow {
  applicationId: number;
  url: string | null;
  location: string | null;
  employment: string | null;
  compensationRaw: string | null;
  compLow: number | null;
  compHigh: number | null;
  fetchedAt: string | null;
  bodyPath: string | null;
}

export interface ContactRow {
  id: number;
  applicationId: number;
  name: string;
  role: string | null;
  linkedin: string | null;
  email: string | null;
  tier: string | null;
  notes: string | null;
}

// ---------------------------------------------------------------------------
// snake_case → camelCase mapping helpers
// ---------------------------------------------------------------------------

function mapApp(row: Record<string, unknown>): AppRow {
  return {
    id: row["id"] as number,
    slug: `${row["company_slug"]}/${row["role_slug"]}`,
    companySlug: row["company_slug"] as string,
    roleSlug: row["role_slug"] as string,
    company: row["company"] as string,
    role: row["role"] as string,
    stage: row["stage"] as string,
    priority: (row["priority"] as number | null) ?? null,
    lastAction: (row["last_action"] as string | null) ?? "—",
    nextStep: (row["next_step"] as string | null) ?? "",
    updated: row["updated"] as string,
    createdAt: row["created_at"] as string,
    notes: (row["notes"] as string | null) ?? null,
  };
}

function mapJd(row: Record<string, unknown>): JdRow {
  return {
    applicationId: row["application_id"] as number,
    url: (row["url"] as string | null) ?? null,
    location: (row["location"] as string | null) ?? null,
    employment: (row["employment"] as string | null) ?? null,
    compensationRaw: (row["compensation_raw"] as string | null) ?? null,
    compLow: (row["comp_low"] as number | null) ?? null,
    compHigh: (row["comp_high"] as number | null) ?? null,
    fetchedAt: (row["fetched_at"] as string | null) ?? null,
    bodyPath: (row["body_path"] as string | null) ?? null,
  };
}

function mapContact(row: Record<string, unknown>): ContactRow {
  return {
    id: row["id"] as number,
    applicationId: row["application_id"] as number,
    name: row["name"] as string,
    role: (row["role"] as string | null) ?? null,
    linkedin: (row["linkedin"] as string | null) ?? null,
    email: (row["email"] as string | null) ?? null,
    tier: (row["tier"] as string | null) ?? null,
    notes: (row["notes"] as string | null) ?? null,
  };
}

// ---------------------------------------------------------------------------
// openDb
// ---------------------------------------------------------------------------

export function dbPathFor(memoryDir: string): string {
  return join(memoryDir, "applications.db");
}

export function openDb(memoryDir: string): Database.Database {
  const dbPath = dbPathFor(memoryDir);
  if (!existsSync(dbPath)) {
    throw new Error(
      `[plytools-viewer] applications.db not found at ${dbPath}.\n` +
        `Run scripts/migrate_to_sqlite.py to create it.`
    );
  }
  const db = new Database(dbPath, { fileMustExist: true });
  db.pragma("journal_mode = WAL");
  db.pragma("foreign_keys = ON");
  db.pragma("busy_timeout = 5000");
  return db;
}

// ---------------------------------------------------------------------------
// Write helpers
// ---------------------------------------------------------------------------

export interface StatusPatch {
  stage?: string;
  priority?: number | null;
  lastAction?: string;
  nextStep?: string;
}

export function patchStatus(
  db: Database.Database,
  companySlug: string,
  roleSlug: string,
  patch: StatusPatch
): void {
  // Build SET clause dynamically from provided fields.
  const sets: string[] = ["updated = date('now')"];
  const params: (string | number | null)[] = [];

  if (patch.stage !== undefined) {
    sets.push("stage = ?");
    params.push(patch.stage);
  }
  if ("priority" in patch) {
    sets.push("priority = ?");
    params.push(patch.priority ?? null);
  }
  if (patch.lastAction !== undefined) {
    sets.push("last_action = ?");
    params.push(patch.lastAction);
  }
  if (patch.nextStep !== undefined) {
    sets.push("next_step = ?");
    params.push(patch.nextStep);
  }

  params.push(companySlug, roleSlug);

  const result = db
    .prepare(
      `UPDATE applications SET ${sets.join(", ")} WHERE company_slug = ? AND role_slug = ?`
    )
    .run(...params);

  if (result.changes === 0) {
    throw new NoSuchApplicationError(`${companySlug}/${roleSlug}`);
  }
}

// ---------------------------------------------------------------------------
// Query helpers
// ---------------------------------------------------------------------------

export function getIndex(db: Database.Database): IndexRow[] {
  const rows = db
    .prepare(
      `SELECT
         a.id,
         a.company_slug,
         a.role_slug,
         a.company,
         a.role,
         a.stage,
         a.priority,
         a.last_action,
         a.next_step,
         a.updated,
         a.created_at,
         a.notes,
         j.location
       FROM applications a
       LEFT JOIN jd j ON j.application_id = a.id
       ORDER BY a.priority ASC NULLS LAST, a.updated DESC`
    )
    .all() as Record<string, unknown>[];

  return rows.map((r) => ({
    ...mapApp(r),
    location: (r["location"] as string | null) ?? null,
  }));
}

export interface ApplicationDetail {
  app: AppRow;
  jd: JdRow | null;
  contacts: ContactRow[];
}

export function getApplication(
  db: Database.Database,
  companySlug: string,
  roleSlug: string
): ApplicationDetail | null {
  const appRow = db
    .prepare(
      `SELECT * FROM applications WHERE company_slug = ? AND role_slug = ?`
    )
    .get(companySlug, roleSlug) as Record<string, unknown> | undefined;

  if (!appRow) return null;

  const app = mapApp(appRow);

  const jdRow = db
    .prepare(`SELECT * FROM jd WHERE application_id = ?`)
    .get(app.id) as Record<string, unknown> | undefined;

  const jd = jdRow ? mapJd(jdRow) : null;

  const contactRows = db
    .prepare(`SELECT * FROM contacts WHERE application_id = ? ORDER BY id ASC`)
    .all(app.id) as Record<string, unknown>[];

  const contacts = contactRows.map(mapContact);

  return { app, jd, contacts };
}
