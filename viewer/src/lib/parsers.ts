import matter from "gray-matter";

export interface KeyedMarkdown {
  fields: Record<string, string>;
  markdown: string;
}

// Bare parse result — the API adds `name` + `raw` before sending to the
// client. Client-side type `ParsedDraft` (in src/lib/types.ts) adds them.
export interface DraftParse {
  frontmatter: Record<string, unknown>;
  body: string;
}

// matches "- **Key:** value" bullets. The key capture excludes `:` and `*`
// to avoid eating the closing `**` when a line has no colon.
const KEY_VALUE_LINE = /^\s*-\s*\*\*([^:*]+):\*\*\s*(.*)$/;

function extractKeyedFields(md: string): Record<string, string> {
  const fields: Record<string, string> = {};
  for (const line of md.split("\n")) {
    const m = line.match(KEY_VALUE_LINE);
    if (m) fields[m[1].trim()] = m[2].trim();
  }
  return fields;
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
