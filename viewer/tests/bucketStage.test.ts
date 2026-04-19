import { describe, it, expect } from "vitest";
import { bucketStage } from "../src/components/StageBadge";

describe("bucketStage", () => {
  const cases: [string, string][] = [
    ["Folder only", "Folder only"],
    ["Discovered", "Discovered"],
    ["JD ingested", "In progress"],
    ["Contacts tiered; awaiting target selection", "In progress"],
    ["JD ingested; awaiting angle confirmation + contact tier list", "In progress"],
    ["Drafts ready", "Drafts ready"],
    ["Draft", "Drafts ready"],
    ["Sent V2 to Julian", "Sent"],
    ["Emailed Head of Design", "Sent"],
    ["Warm-intro requested", "Sent"],
    ["Reply received from CEO", "Replied"],
    ["Interviewing onsite", "Replied"],
    ["Passed by hiring manager", "Replied"],
    ["something completely random", "Discovered"],
  ];
  it.each(cases)("buckets %j as %j", (input, expected) => {
    expect(bucketStage(input)).toBe(expected);
  });
});
