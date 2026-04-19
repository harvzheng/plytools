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

export interface ParsedDraft {
  name: string;
  frontmatter: Record<string, unknown>;
  body: string;
}

export interface Application {
  slug: string;
  status: KeyedMarkdown;
  jd: KeyedMarkdown;
  contacts: { markdown: string };
  drafts: ParsedDraft[];
}

export interface MemoryEvent {
  type: "add" | "change" | "unlink";
  path: string;
}
