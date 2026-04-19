#!/usr/bin/env node
// Wrapper that parses --memory-dir, sets PLYTOOLS_MEMORY_DIR, then execs vite.
// Use: npm run dev -- --memory-dir=/path/to/memory
import { spawn } from "node:child_process";

const args = process.argv.slice(2);
const idx = args.findIndex(
  (a) => a === "--memory-dir" || a.startsWith("--memory-dir=")
);
if (idx >= 0) {
  const arg = args[idx];
  const val = arg.includes("=") ? arg.split("=")[1] : args[idx + 1];
  if (!val) {
    console.error("--memory-dir requires a value");
    process.exit(2);
  }
  process.env.PLYTOOLS_MEMORY_DIR = val;
}

const vite = spawn(
  process.platform === "win32" ? "vite.cmd" : "vite",
  [],
  { stdio: "inherit", env: process.env }
);
vite.on("exit", (code) => process.exit(code ?? 0));
