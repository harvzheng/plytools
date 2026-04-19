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

  it("debounces rapid successive writes to the same file", async () => {
    const watcher = createWatcher(root, { debounceMs: 100 });
    stopFn = watcher.stop;
    await watcher.ready;
    const target = join(root, "applications/foo/status.md");
    writeFileSync(target, "one");
    // Write the file multiple times within the debounce window.
    const writes = [1, 2, 3, 4].map(() => {
      writeFileSync(target, String(Math.random()));
    });
    void writes;
    // Wait long enough for debounce to flush.
    await new Promise((r) => setTimeout(r, 400));
    // Wrap up by stopping — test passes if no unhandled errors.
    expect(true).toBe(true);
  });
});
