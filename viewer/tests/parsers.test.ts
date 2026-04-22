import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  parseDraft,
  parseJd,
} from "../src/lib/parsers";

const read = (p: string) =>
  readFileSync(resolve(__dirname, "fixtures/memory/applications", p), "utf8");

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
