---
name: discover-roles
description: Given a CSV of companies (e.g. `soho-valley.csv`) and/or an article URL listing companies, scan each company's careers page, filter roles for designer+engineer-hybrid fit, present a HITL shortlist, and auto-run job-apply Stage 1 for approved rows. Use when the user pastes a company-list path, mentions "discover roles", "find roles at these companies", or asks to scan multiple companies at once.
---

# Discover-Roles Skill

**Repo root:** the directory containing this `skills/` folder.
**User-data root:** `~/.claude/projects/-Users-harvey-Development-plytools/memory/`.

Deterministic work runs in `scripts/{companies_ingest,resolve_careers,fetch_jobs,shortlist}.py`. Judgment — verifying article company-name candidates, judging role fit, running HITL — happens in-skill.

This skill ends at Stage G by handing off to the `job-apply` skill's Stage 1 for every row the user approves.

## Data layout

| What | Where | Gitignored? |
|------|-------|-------------|
| Careers-URL cache | `<user-data>/applications/_careers_cache.csv` | N/A (not in repo) |
| Per-run shortlist | `<user-data>/applications/_shortlist-<YYYY-MM-DD-HHMM>.md` | N/A |
| Off-limits list | `<user-data>/feedback_off_limits_companies.md` | N/A |
| Existing pipeline | `<user-data>/applications/index.md` | N/A |

## Stages

### Stage A — Ingest

Identify input form(s):
- A local path ending in `.csv` → `uv run scripts/companies_ingest.py csv <path>`
- A URL → `uv run scripts/companies_ingest.py article <url>`; then LLM-filter the returned candidates to real company names (drop phrases like "AI Opportunity", "NYC Renaissance", section headers that look like names).
- Both → run both, merge, dedupe by normalized slug (`re.sub(r"[^a-z0-9]", "", name.lower())`).

Report: "Ingested N companies (X CSV + Y article candidates, deduped)."

### Stage B — Dedup

1. Read the existing pipeline: `uv run scripts/pipeline.py list <user-data>/applications/index.md`. Collect existing company names.
2. Read `<user-data>/feedback_off_limits_companies.md` — parse company names (the memory file has a simple bulleted list).
3. Drop companies matching case-insensitively on name. Report how many dropped by each reason.

### Stage C — Resolve careers URLs

For each remaining company:
1. `uv run scripts/resolve_careers.py "<name>" --cache <user-data>/applications/_careers_cache.csv`
2. If the script returns `source: "unresolved"` with `careers_url: null`, that's a cached negative from a prior run — skip Stage D for this company and surface it in the Stage F unresolved block. Don't re-probe or re-Google.
3. If the script returns `source: "needs_google_or_manual"`:
   - Count it against the session budget (**cap 25 WebSearches per run**).
   - If over budget: skip Google step; this company will surface in the unresolved-block at the end.
   - Otherwise: `WebSearch("<company> careers")`. Pick the first result whose domain is not `linkedin.com`, not `indeed.com`, `glassdoor.com`, `wellfound.com`, or other aggregators. Fetch it via `uv run scripts/fetch_jd.py <url>` (reused as a generic page fetcher); LLM-sniff: does this page look like a careers page with role listings?
   - On YES: record via `uv run scripts/resolve_careers.py --cache <...> --record "<name>" "<url>" generic google` and continue.
   - On NO (or second-choice failure): record as `unresolved` so the skill doesn't re-probe next run — `uv run scripts/resolve_careers.py --cache <...> --record "<name>" "" "" unresolved`.

Report: "N resolved / M unresolved." Keep the unresolved list for Stage F.

### Stage D — Fetch jobs

For each resolved company:
`uv run scripts/fetch_jobs.py <careers_url> --ats <type>`

On any `{"error": ...}` JSON response: log and continue. One company failing does not block the run. Track a per-company role count for the summary.

### Stage E — Filter

Keyword prefilter (do this in-skill as a simple string check — no extra script needed).

Drop titles matching ANY of these, case-insensitive, whole-word where possible:
- **Functions:** `sales`, `marketing`, `recruiter`, `accountant`, `finance`, `legal`, `data scientist`, `ml engineer`, `backend`, `devops`, `sre`, `security`, `qa`, `operations`, `customer success`
- **Levels:** `senior`, `staff`, `principal`, `director`, ` vp `, `head of`, `manager` — UNLESS the title also contains `design` (keep "Design Manager" for LLM judgment).

Then for survivors: LLM fit judgment. Read `<user-data>/profile.md` and `<user-data>/positioning.md` once at the start of this stage. For each `{company, title, snippet}`, output one JSON line:

```json
{"company": "Niva", "title": "Design Engineer", "decision": "fit", "reason": "Design-engineer hybrid, NYC, matches portfolio"}
```

`decision ∈ {fit, maybe, no-fit}`. Only `fit` and `maybe` land on the shortlist. Any unparseable line defaults to `maybe` with reason `"parse fallback"`.

### Stage F — Shortlist write

1. For each kept row: `uv run scripts/shortlist.py append <user-data>/applications/_shortlist-<YYYY-MM-DD-HHMM>.md "<company>" "<title>" "<location>" "<url>" "<reason>"`.
2. Print the shortlist table inline, numbered (`1.`, `2.`, …) so the user can reference by row.
3. Print the unresolved-companies block:
   ```
   Unresolved — paste a careers URL to scan:
   - Matter Bio (https://linkedin.com/company/matter-bio) — "Longevity holding company…"
   - Stepful — "Healthcare education pathways"
   ```

### Stage G — HITL approval

Ask: "Which rows do you want to advance to Stage 1? (row numbers, comma-separated, or 'all', or 'none')"

For each approved row: follow `.claude/skills/job-apply/SKILL.md` Stage 1 in-place (not as a subprocess):
1. `uv run scripts/fetch_jd.py <role_url>` → JD body.
2. Write `<user-data>/applications/<company>/jd.md` and stub `status.md`.
3. Upsert to `<user-data>/applications/index.md` via `uv run scripts/pipeline.py upsert` with stage `Discovered`.

After each approved row: `uv run scripts/shortlist.py set-status <shortlist> <row-index> approved`.
For any rejected rows: `... set-status <row-index> dismissed`.

Do NOT proceed to job-apply Stages 2–5. The user will re-invoke the job-apply skill when ready to do contact discovery and drafts.

## WebSearch budget (critical)

Maintain an in-conversation counter `websearch_used_this_run` starting at 0. Increment by 1 per WebSearch call in Stage C. Hard cap: 25 per run. When hit: stop doing lookups, mark remaining companies unresolved (cached), continue to Stage D.

## Failure handling

- Script JSON `{"error": ...}`: surface to user, skip the affected company, continue.
- No roles found for a company: not an error; counted in "N companies yielded 0 roles".
- Cache-write failure: surface exact path + error; don't fabricate success.

## Never

- Never auto-advance approved rows past Stage 1. Stop after JD ingest + index row.
- Never exceed 25 WebSearches without explicit user approval.
- Never skip the dedup step; re-surfacing companies already in the pipeline wastes the user's attention.
- Never commit `_shortlist-*.md` or `_careers_cache.csv` — they live in user-data and are gitignored by the repo-wide patterns.
