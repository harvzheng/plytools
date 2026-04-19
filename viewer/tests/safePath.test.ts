import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, realpathSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { isInside } from "../server/safePath";

let root: string;

beforeAll(() => {
  root = realpathSync(mkdtempSync(join(tmpdir(), "safepath-")));
  mkdirSync(join(root, "applications/foo"), { recursive: true });
  writeFileSync(join(root, "applications/foo/status.md"), "hi");
});

afterAll(() => {
  rmSync(root, { recursive: true, force: true });
});

describe("isInside", () => {
  it("accepts a path inside root", () => {
    expect(isInside(root, join(root, "applications/foo/status.md"))).toBe(true);
  });

  it("rejects a path outside root", () => {
    expect(isInside(root, "/etc/passwd")).toBe(false);
  });

  it("rejects traversal with ..", () => {
    expect(isInside(root, join(root, "../../etc/passwd"))).toBe(false);
  });

  it("rejects a path that does not exist", () => {
    expect(isInside(root, join(root, "does/not/exist"))).toBe(false);
  });

  it.skipIf(process.platform === "win32")(
    "rejects a symlink inside root that escapes to outside root",
    () => {
      const evil = join(root, "escape");
      symlinkSync("/etc/passwd", evil);
      expect(isInside(root, evil)).toBe(false);
    }
  );
});
