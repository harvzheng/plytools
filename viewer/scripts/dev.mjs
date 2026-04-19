#!/usr/bin/env node
// Wrapper that parses --memory-dir, sets PLYTOOLS_MEMORY_DIR, then execs vite.
// Use: npm run dev -- --memory-dir=/path/to/memory
import { spawn } from "node:child_process";

const args = process.argv.slice(2);
const idx = args.findIndex(
  (a) => a === "--memory-dir" || a.startsWith("--memory-dir=")
);

// Indices of args to drop before forwarding to Vite.
const drop = new Set();

if (idx >= 0) {
  const arg = args[idx];
  const val = arg.includes("=") ? arg.split("=")[1] : args[idx + 1];
  if (!val) {
    console.error("--memory-dir requires a value");
    process.exit(2);
  }
  process.env.PLYTOOLS_MEMORY_DIR = val;
  drop.add(idx);
  // Space-separated form: the next token is the value, not a vite flag.
  if (!arg.includes("=")) drop.add(idx + 1);
}

const viteArgs = args.filter((_, i) => !drop.has(i));

const vite = spawn(
  process.platform === "win32" ? "vite.cmd" : "vite",
  viteArgs,
  { stdio: "inherit", env: process.env }
);

vite.on("error", (err) => {
  if (err.code === "ENOENT") {
    console.error(
      "dev.mjs: could not find 'vite'. Run 'npm install' first."
    );
  } else {
    console.error("dev.mjs: failed to start vite:", err.message);
  }
  process.exit(1);
});

vite.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
  } else {
    process.exit(code ?? 0);
  }
});

for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, () => vite.kill(sig));
}
