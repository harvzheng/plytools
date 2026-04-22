export interface IndexRow {
  // Composite "<companySlug>/<roleSlug>" — used as the selection + query key.
  slug: string;
  companySlug: string;
  roleSlug: string;
  company: string;
  role: string;
  stage: string;
  lastAction: string;
  nextStep: string;
  updated: string;
  // From the `jd` DB table (LEFT JOIN on application id). Falls back to
  // parsing jd.md on disk only for orphan folders that have no DB row.
  // Empty string when missing.
  location: string;
  // From the `applications` DB column. `null` when unset —
  // used to keep blanks at the end when sorting ascending.
  priority: number | null;
}

export interface KeyedMarkdown {
  fields: Record<string, string>;
  markdown: string;
}

export interface ParsedDraft {
  name: string;
  path: string;
  // Full file contents, frontmatter included. Edit mode round-trips through
  // this field so user-only keys in the frontmatter aren't dropped on save.
  raw: string;
  frontmatter: Record<string, unknown>;
  body: string;
}

export interface Application {
  slug: string;
  companySlug: string;
  roleSlug: string;
  dir: string;
  status: KeyedMarkdown;
  jd: KeyedMarkdown;
  contacts: { markdown: string };
  drafts: ParsedDraft[];
}

export interface MemoryEvent {
  type: "add" | "change" | "unlink";
  path: string;
}

export interface SavedView {
  id: number;
  name: string;
  sql: string;
  description: string | null;
  createdAt: string;
  updatedAt: string;
}
