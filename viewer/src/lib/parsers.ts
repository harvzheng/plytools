import matter from "gray-matter";

export interface IndexRow {
  company: string;
  role: string;
  stage: string;
  lastAction: string;
  nextStep: string;
  updated: string;
}

export interface KeyedMarkdown {
  fields: Record<string, string>;
  markdown: string;
}

// Bare parse result — the API adds `name` before sending to the client.
// Client-side type `ParsedDraft` (in src/lib/types.ts) adds that name field.
export interface DraftParse {
  frontmatter: Record<string, unknown>;
  body: string;
}

const INDEX_HEADERS = [
  "Company",
  "Role",
  "Stage",
  "Last action",
  "Next",
  "Updated",
];

export function parseIndex(md: string): IndexRow[] {
  const rows: IndexRow[] = [];
  // Track state: only accept data rows after seeing the correct header + separator
  let seenHeader = false;
  let seenSeparator = false;
  for (const line of md.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("|")) {
      // Non-pipe line resets table context
      seenHeader = false;
      seenSeparator = false;
      continue;
    }
    const cells = trimmed
      .replace(/^\|/, "")
      .replace(/\|$/, "")
      .split("|")
      .map((c) => c.trim());
    // Check for the exact INDEX_HEADERS header row
    if (cells.length === INDEX_HEADERS.length && cells.every((c, i) => c === INDEX_HEADERS[i])) {
      seenHeader = true;
      seenSeparator = false;
      continue;
    }
    // Check for separator row (only dashes/colons/spaces)
    if (seenHeader && cells.every((c) => /^[-:\s]+$/.test(c))) {
      seenSeparator = true;
      continue;
    }
    // Only accept data rows after confirmed header+separator
    if (!seenHeader || !seenSeparator) continue;
    if (cells.length !== INDEX_HEADERS.length) continue;
    rows.push({
      company: cells[0],
      role: cells[1],
      stage: cells[2],
      lastAction: cells[3],
      nextStep: cells[4],
      updated: cells[5],
    });
  }
  return rows;
}

const KEY_VALUE_LINE = /^\s*-\s*\*\*([^:*]+):\*\*\s*(.+)$/;

function extractKeyedFields(md: string): Record<string, string> {
  const fields: Record<string, string> = {};
  for (const line of md.split("\n")) {
    const m = line.match(KEY_VALUE_LINE);
    if (m) fields[m[1].trim()] = m[2].trim();
  }
  return fields;
}

export function parseStatus(md: string): KeyedMarkdown {
  return { fields: extractKeyedFields(md), markdown: md };
}

export function parseJd(md: string): KeyedMarkdown {
  return { fields: extractKeyedFields(md), markdown: md };
}

export function parseDraft(md: string): DraftParse {
  try {
    const parsed = matter(md);
    return {
      frontmatter: parsed.data as Record<string, unknown>,
      body: parsed.content.trimStart(),
    };
  } catch {
    return { frontmatter: {}, body: md };
  }
}
