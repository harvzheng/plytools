import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  parseIndex,
  parseStatus,
  parseDraft,
  parseJd,
} from "../src/lib/parsers";

const read = (p: string) =>
  readFileSync(resolve(__dirname, "fixtures/memory/applications", p), "utf8");

describe("parseIndex", () => {
  it("parses pipe-table rows", () => {
    const rows = parseIndex(read("index.md"));
    expect(rows).toHaveLength(2);
    expect(rows[0]).toEqual({
      company: "Example Co",
      role: "Product Designer",
      stage: "Drafts ready",
      lastAction: "V1 picked for Alex",
      nextStep: "Send V1",
      updated: "2026-04-19",
    });
  });

  it("returns empty array when file has no table", () => {
    expect(parseIndex("no table here")).toEqual([]);
  });

  it("skips malformed rows instead of throwing", () => {
    const md = `| Company | Role |\n|---|---|\n| only one cell\n| A | B | C | D | E | F |\n`;
    expect(parseIndex(md)).toEqual([]);
  });
});

describe("parseStatus", () => {
  it("extracts bold-key bullet fields", () => {
    const parsed = parseStatus(read("example-co/status.md"));
    expect(parsed.fields.Stage).toBe("Drafts ready");
    expect(parsed.fields["Last action"]).toBe(
      "V1 draft picked for Alex Smith — 2026-04-19"
    );
    expect(parsed.fields.Angle).toBe("designer+builder hybrid");
    expect(parsed.markdown).toContain("# Example Co");
  });

  it("returns empty fields when convention missing", () => {
    const parsed = parseStatus("just some prose, no bullets");
    expect(parsed.fields).toEqual({});
    expect(parsed.markdown).toBe("just some prose, no bullets");
  });
});

describe("parseDraft", () => {
  it("splits frontmatter and body", () => {
    const parsed = parseDraft(read("example-co/drafts/alex-hm-v1.md"));
    expect(parsed.frontmatter.persona).toBe("hiring-manager");
    expect(parsed.frontmatter.variant).toBe("v1");
    expect(parsed.body).toContain("**Subject:** hi from harvey");
    expect(parsed.body.startsWith("---")).toBe(false);
  });

  it("returns empty frontmatter when none present", () => {
    const parsed = parseDraft("just a body");
    expect(parsed.frontmatter).toEqual({});
    expect(parsed.body).toBe("just a body");
  });
});

describe("parseJd", () => {
  it("extracts top fact fields and preserves body markdown", () => {
    const parsed = parseJd(read("example-co/jd.md"));
    expect(parsed.fields.URL).toBe("https://example.com/jobs/1");
    expect(parsed.fields.Location).toBe("Remote (United States)");
    expect(parsed.markdown).toContain("## About the Role");
  });
});
