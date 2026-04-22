import type { Plugin, ViteDevServer } from "vite";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { createWatcher } from "./watcher";
import { createApi } from "./api";

export interface PluginOptions {
  memoryDir?: string;
}

function resolveMemoryDir(explicit?: string): string {
  const candidate =
    explicit ||
    process.env.PLYTOOLS_MEMORY_DIR ||
    join(
      homedir(),
      ".claude/projects/-Users-harvey-Development-plytools/memory"
    );
  const abs = resolve(candidate);
  if (!existsSync(abs)) {
    console.warn(
      `[plytools-viewer] memory dir does not exist: ${abs}\n` +
        `Set PLYTOOLS_MEMORY_DIR or pass --memory-dir to override.`
    );
  }
  return abs;
}

export function plytoolsViewer(opts: PluginOptions = {}): Plugin {
  const memoryDir = resolveMemoryDir(opts.memoryDir);
  let currentWatcher: ReturnType<typeof createWatcher> | null = null;

  return {
    name: "plytools-viewer",
    async configureServer(server: ViteDevServer) {
      // Vite may re-invoke configureServer on restart. Stop the prior watcher
      // so we don't leak chokidar instances across config reloads.
      if (currentWatcher) {
        await currentWatcher.stop();
        currentWatcher = null;
      }

      const watcher = createWatcher(memoryDir);
      currentWatcher = watcher;
      const api = createApi({ memoryDir, watcher });

      // Register pre-middleware so /api/* is handled before Vite's
      // HTML/SPA-fallback stack.
      server.middlewares.use((req, res, next) => {
        const url = req.url || "";
        if (url.startsWith("/api/")) {
          api.handler(req, res);
        } else {
          next();
        }
      });

      server.httpServer?.once("close", () => {
        const w = currentWatcher;
        currentWatcher = null;
        void w?.stop();
        api.close();
      });

      console.log(`[plytools-viewer] memory dir: ${memoryDir}`);
    },
  };
}
