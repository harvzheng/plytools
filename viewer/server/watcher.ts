import chokidar, { FSWatcher } from "chokidar";

export interface MemoryEvent {
  type: "add" | "change" | "unlink";
  path: string; // absolute path
}

export interface Watcher {
  on: (listener: (ev: MemoryEvent) => void) => () => void;
  stop: () => Promise<void>;
  ready: Promise<void>;
}

export interface WatcherOptions {
  debounceMs?: number;
}

export function createWatcher(
  root: string,
  opts: WatcherOptions = {}
): Watcher {
  const debounceMs = opts.debounceMs ?? 150;
  const listeners = new Set<(ev: MemoryEvent) => void>();
  const pending = new Map<string, MemoryEvent>();
  let flushTimer: NodeJS.Timeout | null = null;

  const fs: FSWatcher = chokidar.watch(root, {
    ignoreInitial: true,
    ignored: (p) => /(^|[\\/])(node_modules|\.git)([\\/]|$)/.test(p),
    awaitWriteFinish: {
      stabilityThreshold: 50,
      pollInterval: 20,
    },
  });

  const schedule = (ev: MemoryEvent) => {
    // Coalesce by (type, path). Last event wins for that key.
    pending.set(`${ev.type}:${ev.path}`, ev);
    if (flushTimer) return;
    flushTimer = setTimeout(() => {
      const batch = Array.from(pending.values());
      pending.clear();
      flushTimer = null;
      for (const ev of batch) {
        // Snapshot listeners so that unsubscribe/subscribe during dispatch
        // doesn't change who receives this event.
        const snapshot = Array.from(listeners);
        for (const l of snapshot) l(ev);
      }
    }, debounceMs);
  };

  fs.on("add", (p) => schedule({ type: "add", path: p }));
  fs.on("change", (p) => schedule({ type: "change", path: p }));
  fs.on("unlink", (p) => schedule({ type: "unlink", path: p }));

  const ready = new Promise<void>((resolve) => {
    fs.on("ready", () => resolve());
  });

  return {
    on(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    async stop() {
      if (flushTimer) {
        clearTimeout(flushTimer);
        flushTimer = null;
      }
      listeners.clear();
      await fs.close();
    },
    ready,
  };
}
