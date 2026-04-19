# plytools

A Claude Code skill + helper scripts for running job-application outreach
end-to-end: JD ingest → LinkedIn contact tiering → email discovery (Apollo →
Hunter → manual fallback) → persona-tuned draft generation → pipeline
logging. If neither Apollo nor Hunter returns a verified hit, the skill
surfaces a manual lookup block rather than guessing an address.

## How it works

The skill at `.claude/skills/job-apply/` orchestrates a six-stage workflow. Judgment
work (tiering contacts, picking personas, composing drafts) happens in the
model; deterministic work (HTTP, parsing, logging) is done by Python scripts
under `scripts/`.

**Your data is NOT stored in this repo.** Profile, positioning, personal
contacts, and per-application folders all live in Claude's auto-memory at
`~/.claude/projects/-Users-harvey-Development-plytools/memory/`. The repo
contains only tool code, templates, and example schemas.

## Setup

1. Clone this repo into the directory you want Claude Code to treat as the
   project root (the auto-memory path is derived from this path).

2. Install dependencies:

   ```bash
   uv sync --extra dev
   ```

3. Run the interactive setup to configure API keys:

   ```bash
   uv run scripts/setup.py
   ```

   You'll be prompted for each provider. Press Enter to skip either.
   After saving, setup hits each provider's free usage endpoint to confirm
   the keys actually work (no credits burned).

   - Apollo: https://www.apollo.io/pricing (API requires a paid plan)
   - Hunter: https://hunter.io/api (free tier includes API access)

   Both are optional. The skill falls through the cascade and lands on manual
   instructions if no keys are set. You can also skip the script and hand-edit
   `.env` (copy from `.env.example`).

4. In Claude Code, open this repo as the project. On first run, the skill
   will interview you and write `profile.md`, `positioning.md`, and
   `contacts.md` to your auto-memory (not this repo).

## Using the skill

Triggering phrases (any of these work):
- `/job-apply`
- "help me apply to [company]"
- "draft outreach for this role: [URL]"
- "reach out about this: [JD text]"

The skill auto-detects which stage to enter based on what you've shared. You
can jump in at any stage.

### Discover roles across a company list

If you have a CSV of companies (e.g. from Pampam) or a listicle article, ask the
assistant to "discover roles from `<csv-path>`" or "discover roles from
`<article-url>`". The `discover-roles` skill scans each company's careers page,
filters for designer+engineer-hybrid roles, and presents a shortlist for you to
approve. Approved rows drop into the job-apply pipeline at stage "Discovered".

See `.claude/skills/discover-roles/SKILL.md` for the full stage flow.

## Running scripts directly

Each script in `scripts/` is a standalone `uv` script:

```bash
uv run scripts/fetch_jd.py https://boards.greenhouse.io/example/jobs/1
uv run scripts/apollo_lookup.py lookup Alex Chen example.com
uv run scripts/hunter_lookup.py credits
uv run scripts/pipeline.py list ~/.claude/projects/-Users-harvey-Development-plytools/memory/applications/index.md
```

## Testing

```bash
uv run pytest
```

Tests use `respx` to mock HTTP — no live API keys required to run the suite.

## Safety

Before making this repo public, verify:
- `.env` is not tracked
- No `applications/`, `memory/`, or personal PDFs tracked
- Run `git log --all --full-history -- "*.env"` and confirm no secret history

## Acknowledgments

Built with Claude Code.
