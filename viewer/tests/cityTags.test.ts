import { describe, it, expect } from "vitest";
import { cityTags } from "../src/lib/cityTags";

describe("cityTags", () => {
  const cases: Array<[string, string[]]> = [
    ["New York, NY (HQ)", ["NYC"]],
    ["NYC", ["NYC"]],
    ["Brooklyn, NY", ["NYC"]],
    ["Union Square, New York City", ["NYC"]],
    ["San Francisco", ["Bay Area"]],
    ["SF", ["Bay Area"]],
    ["Mountain View, California", ["Bay Area"]],
    ["Seattle, Washington", ["Seattle"]],
    ["Boston", ["Boston"]],
    ["Remote (US)", ["Other US", "Remote"]],
    ["Remote (North America)", ["Other US", "Remote"]],
    ["Remote, Americas", ["Other US", "Remote"]],
    ["Pittsburgh", ["Other US"]],
    ["Washington, D.C.", ["Other US"]],
    ["SF, Seattle, New York, Remote in the US", ["NYC", "Bay Area", "Seattle", "Remote"]],
    ["NYC / SF", ["NYC", "Bay Area"]],
    ["", ["Unknown"]],
    ["Mars Colony", ["Unknown"]],
  ];
  it.each(cases)("tags %j as %j", (input, expected) => {
    expect(cityTags(input)).toEqual(expected);
  });

  it("demotes Other US when a specific US city already matched", () => {
    // "New York, United States" hits both NYC and the generic US pattern;
    // the result should drop "Other US" since NYC is more specific.
    const tags = cityTags("New York, United States");
    expect(tags).toContain("NYC");
    expect(tags).not.toContain("Other US");
  });
});
