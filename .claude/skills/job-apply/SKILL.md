---
name: job-apply
description: End-to-end job-application outreach. Use when the user pastes a JD URL, mentions applying to a company, asks for outreach drafts, or says things like "help me reach out to [company]", "draft an email to the hiring manager at [company]", or "apply to this role". Orchestrates six stages — profile intake, JD ingest, LinkedIn contact filtering, HITL target selection, email discovery via Apollo/Hunter (falling back to manual when neither finds a verified hit), persona-tuned draft generation, and pipeline logging — with user data isolated in auto-memory and tool code in this repo.
---

# Job-Apply Skill

**Repo root:** the directory containing this `skills/job-apply/` folder.
**User-data root:** `~/.claude/projects/-Users-harvey-Development-plytools/memory/`.

All deterministic work happens in `scripts/*.py`. Judgment — tiering contacts,
picking personas, composing drafts — happens in-skill (LLM reasoning).

## Data layout

| What | Where | Gitignored? |
|------|-------|-------------|
| API keys | `<repo>/.env` | yes |
| Profile / positioning / contacts | `<user-data>/{profile,positioning,contacts}.md` | N/A (not in repo) |
| Per-company application folders | `<user-data>/applications/<company>/` | N/A |
| Pipeline index | `<user-data>/applications/index.md` | N/A |

## Stages (auto-detect which to enter)

Infer stage from conversation context:
- User pastes a JD URL or text → Stage 1
- User pastes a tier list or names with titles → Stage 2
- A tier list already exists in the conversation → Stage 2.5
- User picks targets → Stage 3
- Emails in context, user asks for drafts → Stage 4

If `profile.md` is missing, run **Stage 0** before anything else.

### Stage 0 — Profile intake (one-time)

Trigger: `profile.md` missing in user-data, or user says "update my profile".

1. Read `positioning.md` if it exists; note any `local_path` under Portfolio source.
2. Run: `uv run scripts/resume_parse.py <path-or-url>`
3. Fetch portfolio content:
   - If `local_path` set and exists → read the repo directly (look for README, `content/`, `src/pages`, project write-ups).
   - Otherwise → `uv run scripts/fetch_jd.py <url>` (reused as a generic page fetcher) on the portfolio URL.
4. Interview the user for `positioning.md`:
   - The pitch (one-liner)
   - Angles by role type (design-led, eng-led, founding/generalist)
   - Tone preferences
   - "Always include" and "Never" rules (layered on top of `templates/prompt.md`)
5. Interview for initial `contacts.md` entries.
6. Write all three files + add pointer lines to `MEMORY.md`.

### Stage 1 — JD ingest

Inputs: URL (preferred) or pasted text.

1. If URL: `uv run scripts/fetch_jd.py <url>`. If the script returns an
   `{"error": "..."}` JSON (auth wall, etc.), ask the user to paste the JD
   text directly.
2. If text: skip the script; extract title/company/location/body yourself and
   note domain if visible.
3. Ask which angle to emphasize. Default from `positioning.md` angles-by-role-type,
   but let the user override per-role.
4. Write `applications/<company>/jd.md` and a stub `status.md`.

### Stage 2 — Contact filter

Inputs: pasted LinkedIn names + titles (freeform).

1. Parse the paste into `{name, title}` records. Tolerate any reasonable format
   (one per line, comma-separated, tabular).
2. Tier each person (judgment, not code):
   - 🎯 **Primary** — role owner for this JD. For a design role, prefer Head of
     Design over the CTO even if the CTO signed the JD.
   - 🤝 **Warm-intro** — cross-reference against `contacts.md`. Match by name.
   - 📋 **Context** — same-function peers.
   - ❌ **Skip** — unrelated functions.
3. Print the tiered list with a one-line "why" per person.
4. Write `applications/<company>/contacts.md`.

### Stage 2.5 — Target selection (HITL gate)

**Never auto-pick targets.** Ask the user explicitly:

> "Who do you want to reach out to? Pick any number — I'll run email discovery
> and draft only for the names you choose."

Only the selected names flow into Stage 3 and Stage 4.

### Stage 3 — Email discovery (per target)

Session credit counter: track across Stages 3 invocations within this
conversation. Hard-stop at 10 credits total; ask before continuing.

For each selected target, run the cascade:

1. **Apollo** — `uv run scripts/apollo_lookup.py lookup <first> <last> <domain>`.
   - Before first call this session, run `apollo_lookup.py credits`. If
     remaining < 5, warn the user and ask before proceeding.
   - On 402/429/out-of-credits error, skip to Hunter.
2. **Hunter** — `uv run scripts/hunter_lookup.py lookup <first> <last> <domain>`.
   - Same credit-floor check against `hunter_lookup.py credits`.
   - On quota/error or miss, skip to manual.
3. **Manual** — print a copy-paste block:
   - Apollo web UI search link: `https://app.apollo.io/#/people?qKeywords=<name>&qOrganizationName=<company>`
   - Hunter web UI: `https://hunter.io/search/<domain>`
   - LinkedIn Sales Nav hint

Only verified hits from Apollo or Hunter are recorded as usable emails. If both
providers miss, surface the manual block and do NOT fabricate an address —
guessing is explicitly out of scope.

After each lookup, increment the session credit counter by 1 and append a row to
`applications/<company>/contacts.md`:

```
| Name | Title | Tier | Email | Source | Confidence |
```

### Stage 4 — Draft generation

For each selected target:

1. Pick persona template from (tier, JD signal):
   - 🤝 Warm-intro → `templates/warm_intro_ask.md`
   - 🎯 Primary + design role → `templates/cold_hiring_manager.md`
   - 🎯 Primary + eng/exec role → `templates/cold_exec.md`
   - 📋 Context → `templates/cold_peer.md`
2. Read `templates/prompt.md` + chosen persona template + `profile.md` +
   `positioning.md` + `jd.md`.
3. Compose two variants (v1 and v2) per the persona's variant guidance.
4. Write both to `applications/<company>/drafts/<name>-<persona>-v1.md` and
   `-v2.md`. Print both inline.
5. Ask the user which variant to use or if they want another revision.

### Stage 5 — Pipeline update

1. Determine stage string from what was actually done this session (e.g.,
   "Drafts ready", "Warm-intro requested", "Emailed Head of Design").
2. Run: `uv run scripts/pipeline.py append <user-data>/applications/index.md <company> <role> <stage> "<last_action>" "<next_step>" <today>`
3. Print the current pipeline table.

## Credit-budget enforcement (critical)

Maintain an in-conversation counter `credits_used_this_session` starting at 0.
Increment by 1 per successful Apollo or Hunter lookup call (manual output is
free). Before every lookup:

- If `credits_used_this_session >= 10`: **stop**, show the counter, ask the
  user whether to continue. Only proceed on explicit approval.

## Environment variables

Read `.env` at the repo root (if present). Expected:
- `APOLLO_API_KEY` — required for Apollo cascade step
- `HUNTER_API_KEY` — required for Hunter cascade step

Both are optional; the skill falls through the cascade and eventually lands on
manual output if neither is set.

## Failure handling

- Script error (JSON `{"error": ...}`): surface to user. Do not silently retry.
- Network/timeout: offer to retry once; otherwise skip to next cascade step.
- File-write failure on auto-memory paths: surface the exact path and error;
  don't fabricate success.

## Never

- Never auto-select targets for outreach.
- Never commit `applications/`, `profile.md`, `positioning.md`, `contacts.md`,
  or `.env` to the repo.
- Never claim an email is verified unless the script returned
  `confidence: "verified"` or equivalent.
- Never guess or fabricate an email address. If Apollo and Hunter both miss,
  surface the manual lookup block instead.
- Never exceed the 10-credit session cap without explicit user approval.
