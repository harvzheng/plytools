# Job-Apply Skill — Design

**Status:** approved
**Date:** 2026-04-18
**Owner:** Harvey Zheng

## Problem

Applying to jobs is a repetitive multi-step workflow: read a JD, identify the right people to reach out to, discover their emails, and draft outreach tuned to each recipient. Done by hand, every application costs an hour of friction-heavy work. The judgment parts (who's the right target, how to frame a pitch) are the valuable part; the mechanical parts (parsing JDs, calling Apollo, formatting drafts, tracking pipeline) are pure overhead.

Goal: a Claude Code skill that takes a JD and a pasted LinkedIn contact list and produces a tiered contact plan, verified emails, and personalized drafts — while keeping user data safely separated from open-source tool code.

## Scope

In scope for v1:
- One orchestrating skill (`job-apply`) with six internal stages, entrable at any stage
- Helper Python scripts for deterministic work (JD fetch, Apollo/Hunter lookups, resume parse, pipeline log)
- Memory schemas for profile, positioning, personal contacts
- Per-application folders + pipeline index
- Persona-aware draft templates with a shared drafting prompt
- API cascade (Apollo → Hunter → pattern-guess → manual) with a 10-credit per-session cap

Explicit non-goals for v1:
- Browser extension for LinkedIn capture (see Future Work)
- Follow-up reminder automation
- Multi-profile / A/B positioning support
- CRM or Sheets export

## Architecture

### Repo layout (open-source)

```
plytools/
├── skills/
│   └── job-apply/
│       └── SKILL.md
├── scripts/                               # uv single-file scripts
│   ├── fetch_jd.py
│   ├── apollo_lookup.py
│   ├── hunter_lookup.py
│   ├── email_fallback.py
│   ├── resume_parse.py
│   └── pipeline.py
├── templates/
│   ├── prompt.md                          # shared drafting rules (hard nevers, tone)
│   ├── warm_intro_ask.md
│   ├── cold_hiring_manager.md
│   ├── cold_peer.md
│   └── cold_exec.md
├── schemas/                               # examples for adopters
│   ├── profile.example.md
│   ├── positioning.example.md
│   └── contacts.example.md
├── tests/                                 # pytest + vcrpy cassettes
├── .env.example
├── .gitignore
├── README.md
└── pyproject.toml
```

### User-data layout (auto-memory, not in repo)

```
~/.claude/projects/-Users-harvey-Development-plytools/memory/
├── MEMORY.md
├── profile.md
├── positioning.md
├── contacts.md
└── applications/
    ├── index.md                           # pipeline dashboard
    └── <company>/
        ├── jd.md
        ├── contacts.md
        ├── status.md
        └── drafts/
            ├── <name>-<persona>-v1.md
            └── <name>-<persona>-v2.md
```

### Data split

- **Tool code + schemas + examples** → repo (public)
- **Profile, positioning, personal contacts, applications log, drafts** → auto-memory (private)
- **`.env` (API keys)** → repo root, gitignored

## Stages

The skill figures out which stage to enter from conversation context; user can start anywhere.

### Stage 0 — Profile intake (one-time, lazy)

Triggers when `profile.md` is missing or user says "update my profile."

Actions:
1. `resume_parse.py` on the resume URL (or local path if `positioning.md` sets one)
2. Fetch portfolio content — prefer `positioning.md:local_path` if set, else scrape URL
3. Interview user for `positioning.md`: one-liner pitch, angles by role type, tone prefs, "always include" and "never" rules
4. Interview for initial `contacts.md` entries

Output: writes `profile.md`, `positioning.md`, `contacts.md` to auto-memory + pointer lines in `MEMORY.md`.

### Stage 1 — JD ingest

Input: JD URL (preferred) or pasted text.

Actions:
1. `fetch_jd.py <url>` → structured JD (title, company, location, requirements, named people, company domain)
2. If URL fetch thin or fails (e.g., LinkedIn JDs), prompt user for pasted text
3. Ask user which angle to emphasize (default from `positioning.md`, overridable)

Output: `applications/<company>/jd.md` + stub `status.md`.

### Stage 2 — Contact filter

Input: pasted LinkedIn names + titles (freeform text, tolerant parser).

Actions:
1. Parse the paste into `[{name, title, ...}]`
2. Tier each person:
   - 🎯 **Primary** — role owner for this JD (e.g., Head of Design for a design role, even if the JD is signed by the CTO)
   - 🤝 **Warm-intro** — cross-referenced against `contacts.md`
   - 📋 **Context** — same-function peers (culture/team signal, not reach-out targets)
   - ❌ **Skip** — unrelated functions
3. Show tiered list with a one-line "why" per person

Output: `applications/<company>/contacts.md` with the tiered list.

### Stage 2.5 — Target selection (HITL gate)

The skill proposes; the user decides. After Stage 2 prints tiers, skill asks *"Who do you want to reach out to? Pick any number."*. Only selected names flow into Stage 3 and Stage 4. Skill never auto-picks targets.

### Stage 3 — Email discovery

Runs per-target, not per-batch (partial failures don't waste credits).

Cascade:
1. **Apollo** (`APOLLO_API_KEY`) — `people/match` with first + last + company domain
2. **Hunter** (`HUNTER_API_KEY`) — `email-finder`, fallback on Apollo miss or credit exhaustion
3. **Pattern-guess** — Hunter `domain-search` returns dominant pattern; apply to each name. Flag as unverified.
4. **Manual** — skill prints copy-paste block with Apollo UI URL, Hunter UI URL, LinkedIn Sales Nav hint

Credit handling (two independent guardrails):
1. **Provider credit floor.** Before each call, query the provider's `usage` endpoint; if the provider's remaining credits drop below 5, warn the user and ask before proceeding.
2. **Session cap.** The skill tracks credits spent during the current Claude Code conversation. When the running total hits 10, hard-stop and ask before continuing. The counter resets each new conversation.

Errors: 402 / 429 / out-of-credits → automatic skip to next provider in the cascade.

Output: appends rows to `applications/<company>/contacts.md`:
```markdown
| Name | Title | Tier | Email | Source | Confidence |
```

Scripts return JSON to stdout: `{email, source, confidence, credits_remaining}`.

### Stage 4 — Draft generation

For each selected target:
1. Pick persona template from tier + JD signal
2. Generate two variants using `templates/prompt.md` (shared rules) + persona template + profile + positioning + JD
3. Save as `applications/<company>/drafts/<name>-<persona>-v1.md` and `-v2.md`
4. Print both inline; user picks, requests another, or edits

Persona mapping:

| Tier | Persona | Template |
|------|---------|----------|
| 🤝 Warm-intro | Personal contact | `warm_intro_ask.md` |
| 🎯 Primary (design-led role) | Hiring manager / Head of Design | `cold_hiring_manager.md` |
| 🎯 Primary (eng-led role) | Eng manager / CTO | `cold_exec.md` |
| 📋 Context | Peer designer/engineer | `cold_peer.md` |

Variant strategy:
- v1: template default angle (e.g., portfolio-led)
- v2: alternate angle (e.g., unicorn-first + ship-to-prod angle)

### Stage 5 — Pipeline update

`pipeline.py` appends a row to `applications/index.md` and prints current pipeline:

```markdown
| Company  | Role              | Stage                | Last action       | Next         | Updated    |
|----------|-------------------|----------------------|-------------------|--------------|------------|
| Profound | Product Designer  | Warm-intro requested | Emailed Praneeth  | Wait 3 days  | 2026-04-18 |
```

## Memory schemas

### `profile.md` (type: user)

```markdown
## Experience
- [Role] at [Company] (YYYY–YYYY) — 2-3 bullets on shipped work + impact

## Projects (portfolio highlights)
- [Project] — one-line description + URL + tags (design/eng/both)

## Skills
Design: ...
Engineering: ...
Tools: ...
```

### `positioning.md` (type: user)

```markdown
## The pitch (one-liner)
"Unicorn designer+engineer hybrid — I prototype in code and ship to prod."

## Angles by role type
- Design-led role → foreground craft, use unicorn framing as bonus (not lede)
- Eng-led role → foreground shipping, design as "also"
- Founding / generalist → lead with unicorn framing

## Tone
Crisp, specific, no corporate fluff. First person. Skim-friendly.

## Always include
- Link to harveyzheng.com
- One concrete project matched to the JD

## Portfolio source (optional)
local_path: /Users/harvey/Development/personal-site-v2
url: https://harveyzheng.com
```

### `contacts.md` (type: reference)

```markdown
| Name | Current company | Relationship | Last contact | Notes |
|------|-----------------|--------------|--------------|-------|
| Praneeth Alla | Profound | UPenn M&TSI summer camp 2018 | 2026-04 | LinkedIn connected, have phone |
```

## Templates

Templates are **skeletons, not fill-in-the-blanks**: they set structure, tone, length, and hard rules; the LLM composes using profile + positioning + JD context.

### `templates/prompt.md` (shared)

Contains universal drafting rules that apply to every variant:
- Hard "never" list (no "I hope this finds you well", no "passionate", no "synergy", no mention of salary in first touch)
- Hard "always" list (include harveyzheng.com link; match one specific thing to the JD)
- Default tone (crisp, specific, lowercase-ish when casual)
- Subject line constraints (under 50 chars, specific to the role)
- User can edit this file anytime to adjust global style without touching per-persona templates

### Per-persona templates

Each template has frontmatter (persona, length, tone) and four sections: Intent, Rules, Structure, and an optional example. Example from `cold_hiring_manager.md`:

```markdown
---
persona: hiring-manager
length: 80-120 words
tone: crisp, specific, no corporate fluff
---

# Intent
Land a reply. Not a full pitch — enough to make them want to see more.

# Rules
- Subject: under 50 chars, specific to this role
- Open: lead with a reason you're writing *this* person about *this* role
- Middle: ONE concrete project/skill matched to their JD, linked
- Close: low-friction CTA (15-min chat, or "happy to send a Loom walkthrough")

# Structure
Hook (1 line) → Fit (2 lines, 1 specific project) → CTA (1 line) → Sign-off + link
```

## Error handling

- **Scripts validate at I/O boundaries only** (bad API key, 401, network failure, malformed API response). Internal trust.
- **LLM never second-guesses script output.** If `apollo_lookup.py` returns `email: null`, the skill surfaces it; doesn't confabulate.
- **Script failures surface to user**, don't silently fall back. Cascade fallback is explicit in the script's return value (`source: "hunter"` vs `"apollo"`), not hidden.
- **Credit-budget overrun = hard stop.** Asks user before proceeding past 10 credits.

## Testing

- `pytest` unit tests against VCR-recorded API fixtures — no real credits burned in tests
- Mock JD HTML fixtures for Greenhouse, Lever, Ashby shapes
- Resume parser tested against one real PDF fixture (gitignored; tests use a sanitized copy in `tests/fixtures/`)
- No LLM behavior tests — LLM output is judgment, not code

## Open-source safety

Before making the repo public:
- `.gitignore` covers: `.env`, `data/`, `applications/`, `memory/`, `*.pdf`, `*.docx`
- Optional pre-commit hook scans for Apollo/Hunter key prefixes
- `README.md` documents: "your data lives in auto-memory; this repo holds only tool code"
- Examples use `EXAMPLE_NAME`, `example.com`, fake emails — never real

## Invocation

User triggers the skill by:
- Typing `/job-apply`
- Saying things like "help me apply to [company]" or "draft outreach for this role"

Skill frontmatter description triggers on: *"apply to", "reach out about", "outreach for", "help me email [company]"*.

Skill auto-detects stage from conversation context (URL pasted = Stage 1, tier list present = Stage 2.5, etc.).

## Dependencies

- Python 3.11+ (uv for single-file script metadata)
- `httpx` for HTTP, `pydantic` for schemas, `pypdf` for resume parse, `beautifulsoup4` for JD HTML
- `pytest` + `vcrpy` for tests

## Future work (post-v1)

- **Browser extension** for LinkedIn capture — solves paste friction, but Apollo's own Chrome extension covers most of the need; revisit if paste genuinely bottlenecks
- **Follow-up reminder cron** using the `schedule` skill
- **Multi-profile support** for A/B positioning experiments
- **CRM / Sheets sync** for the pipeline log

## Success criteria

- New user can set up from a clean repo + empty auto-memory in under 10 minutes
- Reaching Stage 4 (drafts ready) for a new role takes under 5 minutes of active time
- Draft quality is high enough that at least one of v1/v2 is usable with minor edits
- No personal data ever ends up in the public repo's git history
