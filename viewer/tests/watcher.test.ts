import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync, writeFileSync, mkdirSync, realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createWatcher, MemoryEvent } from "../server/watcher";

let root: string;
let stopFn: () => Promise<void>;

beforeEach(() => {
  root = realpathSync(mkdtempSync(join(tmpdir(), "watcher-")));
  mkdirSync(join(root, "applications/foo"), { recursive: true });
});

afterEach(async () => {
  if (stopFn) await stopFn();
  rmSync(root, { recursive: true, force: true });
});

async function collect(
  watcher: ReturnType<typeof createWatcher>,
  n: number,
  timeoutMs = 2000
): Promise<MemoryEvent[]> {
  return new Promise((resolve, reject) => {
    const seen: MemoryEvent[] = [];
    const t = setTimeout(
      () => reject(new Error(`timed out waiting for ${n} events`)),
      timeoutMs
    );
    watcher.on((ev) => {
      seen.push(ev);
      if (seen.length >= n) {
        clearTimeout(t);
        resolve(seen);
      }
    });
  });
}

describe("createWatcher", () => {
  it("emits a change event when a watched file is written", async () => {
    const watcher = createWatcher(root);
    stopFn = watcher.stop;
    await watcher.ready;
    const pending = collect(watcher, 1);
    writeFileSync(join(root, "applications/foo/status.md"), "hi");
    const events = await pending;
    expect(events[0].type).toBe("add");
    expect(events[0].path).toContain("applications/foo/status.md");
  });

  it("still emits events for paths containing 'git' or 'node' substrings", async () => {
    mkdirSync(join(root, "applications/gitlab-co"), { recursive: true });
    const watcher = createWatcher(root);
    stopFn = watcher.stop;
    await watcher.ready;
    const pending = collect(watcher, 1);
    writeFileSync(join(root, "applications/gitlab-co/status.md"), "hi");
    const events = await pending;
    expect(events[0].path).toContain("gitlab-co/status.md");
  });
});
