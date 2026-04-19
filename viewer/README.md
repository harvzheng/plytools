# plytools viewer

Local browser UI for the job-apply pipeline. Reads markdown files from
the Claude auto-memory dir and shows them as an Airtable-style table
plus a per-application detail pane. Hot-reloads when files change.

## Quick start

```bash
cd viewer
npm install
npm run dev
```

Open http://localhost:5173.

## Memory dir resolution

The viewer reads from (in order):

1. `--memory-dir=<path>` CLI flag: `npm run dev -- --memory-dir=/custom/path`
2. `PLYTOOLS_MEMORY_DIR` environment variable
3. Default: `~/.claude/projects/-Users-harvey-Development-plytools/memory/`

## What's read-only vs write

**Read-only:** the index table, all detail tabs, all rendered drafts.
The UI never mutates files in the memory dir.

**Write-ish (but safe):**
- **Copy draft** — copies to the OS clipboard; no server write.
- **Open in editor / Open folder** — spawns `$EDITOR` (or `code` if
  unset) on a path that the server has verified sits inside the
  configured memory dir.

## Testing

```bash
cd viewer
npm test
```

Covers parsers, safePath containment, the watcher, and the API
handlers (including path-traversal rejection on `/api/open`).

## Architecture

Single Vite dev server. A custom plugin (`server/plugin.ts`) adds
chokidar-backed API middleware and an SSE endpoint. React app consumes
both via `@tanstack/react-query`. See
`docs/superpowers/specs/2026-04-19-applications-viewer-design.md`
for the full design.
