# Job-Apply Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude Code skill that orchestrates end-to-end job-application outreach — JD ingest, LinkedIn contact tiering, email discovery with provider cascade, and persona-tuned draft generation — with tool code in a public repo and user data isolated in auto-memory.

**Architecture:** An orchestrating `SKILL.md` drives a six-stage workflow and delegates deterministic work to Python single-file scripts (JD fetch, Apollo/Hunter lookup, pattern guess, resume parse, pipeline log). Per-persona Markdown templates plus a shared `prompt.md` steer draft composition. All user data (profile, contacts, application folders, drafts) lives in `~/.claude/projects/-Users-harvey-Development-plytools/memory/`; the repo contains only code, templates, and example schemas.

**Tech Stack:**
- Python 3.11+ with `uv` PEP 723 headers for single-file script portability
- `httpx` (HTTP), `pydantic` (schemas), `pypdf` (resume parse), `beautifulsoup4` (JD HTML)
- `pytest` + `respx` for tests (respx substitutes cleanly for the spec's `vcrpy` — no live API keys needed to develop; HTTP behaviour is mocked with fixed responses)
- Markdown for SKILL.md, templates, schema examples, and memory files

**Spec reference:** `docs/superpowers/specs/2026-04-18-job-apply-skill-design.md`

---

## File structure (what each file owns)

```
plytools/
├── skills/
│   └── job-apply/
│       └── SKILL.md                 # Orchestrator: stages, handoffs, HITL gates
├── scripts/                         # All standalone + importable; PEP 723 headers
│   ├── pipeline.py                  # read/append applications/index.md
│   ├── fetch_jd.py                  # URL → structured JD
│   ├── resume_parse.py              # PDF path or URL → structured resume
│   ├── apollo_lookup.py             # people/match + credits check
│   ├── hunter_lookup.py             # email-finder, domain-search, account
│   └── email_fallback.py            # apply email pattern to name + domain
├── templates/
│   ├── prompt.md                    # shared drafting rules (never/always/tone)
│   ├── warm_intro_ask.md            # personal contact asking for intro
│   ├── cold_hiring_manager.md       # primary design-role target
│   ├── cold_exec.md                 # CTO/founder, eng-led angle
│   └── cold_peer.md                 # same-function, no-ask message
├── schemas/
│   ├── profile.example.md           # adopter-facing profile schema
│   ├── positioning.example.md       # adopter-facing positioning schema
│   └── contacts.example.md          # adopter-facing contacts schema
├── tests/
│   ├── conftest.py                  # adds ../scripts to sys.path
│   ├── fixtures/
│   │   ├── jd_greenhouse.html       # sample JD HTML
│   │   ├── jd_lever.html
│   │   ├── jd_ashby.html
│   │   └── resume_sample.pdf        # (gitignored; placeholder in repo)
│   ├── test_pipeline.py
│   ├── test_fetch_jd.py
│   ├── test_resume_parse.py
│   ├── test_apollo_lookup.py
│   ├── test_hunter_lookup.py
│   └── test_email_fallback.py
├── pyproject.toml                   # dev deps: pytest, respx, httpx, beautifulsoup4, pypdf, pydantic
├── .env.example
├── .gitignore
└── README.md
```

Each script has one responsibility. Scripts share no runtime state — the orchestrating `SKILL.md` passes data between them via stdin/stdout JSON. That keeps each unit testable in isolation.

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `tests/conftest.py`
- Create: `tests/fixtures/.gitkeep`
- Create: `scripts/.gitkeep` (placeholder; removed in later tasks when scripts land)

- [ ] **Step 1: Create `.gitignore` (critical for open-source safety)**

```gitignore
# Secrets
.env
.env.local
.env.*.local

# User data — must NEVER be committed
data/
applications/
memory/
profile.md
positioning.md
contacts.md

# Personal documents
*.pdf
*.docx
!tests/fixtures/*.pdf

# Python
__pycache__/
*.pyc
.pytest_cache/
.venv/
venv/
.uv/
dist/
build/
*.egg-info/

# OS / editors
.DS_Store
.idea/
.vscode/
*.swp
```

- [ ] **Step 2: Create `.env.example`**

```bash
# Apollo.io — https://developer.apollo.io/
APOLLO_API_KEY=

# Hunter.io — https://hunter.io/api
HUNTER_API_KEY=
```

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[project]
name = "plytools"
version = "0.1.0"
description = "Claude Code skill + scripts for job-application outreach"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",
    "pydantic>=2.6",
    "beautifulsoup4>=4.12",
    "pypdf>=4.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "respx>=0.21",
    "reportlab>=4.0",  # test-only: generate resume PDF fixture
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["scripts"]
```

- [ ] **Step 4: Create `tests/conftest.py`**

```python
"""Shared pytest config. Adds scripts/ to sys.path so tests can import scripts as modules."""
import pathlib
import sys

SCRIPTS_DIR = pathlib.Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
```

- [ ] **Step 5: Create placeholder files so directories track**

```bash
mkdir -p tests/fixtures scripts
touch tests/fixtures/.gitkeep scripts/.gitkeep
```

- [ ] **Step 6: Verify Python + uv available and install dev deps**

Run: `uv sync --extra dev`
Expected: creates `.venv/`, installs all deps. If `uv` missing, install via `brew install uv` first.

- [ ] **Step 7: Commit**

```bash
git add .gitignore .env.example pyproject.toml tests/conftest.py tests/fixtures/.gitkeep scripts/.gitkeep
git commit -m "chore: project scaffolding (pyproject, gitignore, test config)"
```

---

## Task 2: `pipeline.py` — applications log reader/writer

Handles `applications/index.md` — the markdown-table dashboard of active applications. No network, pure file I/O. Good first script because it exercises the testing pattern without HTTP.

**Files:**
- Create: `scripts/pipeline.py`
- Create: `tests/test_pipeline.py`
- Delete: `scripts/.gitkeep`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pipeline.py`:

```python
"""Tests for pipeline.py — application index read/append."""
from __future__ import annotations
import pathlib
import pytest

from pipeline import Row, append_row, read_index, render_index


def test_read_index_missing_file_returns_empty(tmp_path: pathlib.Path):
    assert read_index(tmp_path / "index.md") == []


def test_append_row_creates_file_with_header(tmp_path: pathlib.Path):
    path = tmp_path / "index.md"
    row = Row(
        company="Profound",
        role="Product Designer",
        stage="Warm-intro requested",
        last_action="Emailed Praneeth",
        next_step="Wait 3 days",
        updated="2026-04-18",
    )
    append_row(path, row)
    content = path.read_text()
    assert "| Company |" in content
    assert "Profound" in content
    assert "Product Designer" in content


def test_append_row_preserves_existing_rows(tmp_path: pathlib.Path):
    path = tmp_path / "index.md"
    r1 = Row("A", "Designer", "Draft", "None", "Send", "2026-04-17")
    r2 = Row("B", "Engineer", "Sent", "Emailed CTO", "Follow up", "2026-04-18")
    append_row(path, r1)
    append_row(path, r2)
    rows = read_index(path)
    assert len(rows) == 2
    assert rows[0].company == "A"
    assert rows[1].company == "B"


def test_render_index_formats_table(tmp_path: pathlib.Path):
    rows = [
        Row("A", "Designer", "Draft", "None", "Send", "2026-04-17"),
        Row("B", "Engineer", "Sent", "Emailed CTO", "Follow up", "2026-04-18"),
    ]
    out = render_index(rows)
    lines = out.strip().splitlines()
    # header + separator + 2 rows
    assert len(lines) == 4
    assert lines[0].startswith("| Company")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: ImportError / ModuleNotFoundError for `pipeline`.

- [ ] **Step 3: Implement `scripts/pipeline.py`**

```python
#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# ///
"""pipeline.py — read/append the applications/index.md markdown table.

Usage:
  uv run scripts/pipeline.py append <index.md> <company> <role> <stage> <last> <next> <updated>
  uv run scripts/pipeline.py list <index.md>
"""
from __future__ import annotations

import argparse
import pathlib
import sys
from dataclasses import asdict, dataclass, fields

HEADERS = ["Company", "Role", "Stage", "Last action", "Next", "Updated"]


@dataclass
class Row:
    company: str
    role: str
    stage: str
    last_action: str
    next_step: str
    updated: str


def _header_line() -> str:
    return "| " + " | ".join(HEADERS) + " |"


def _separator_line() -> str:
    return "|" + "|".join(["---"] * len(HEADERS)) + "|"


def render_index(rows: list[Row]) -> str:
    lines = [_header_line(), _separator_line()]
    for r in rows:
        lines.append("| " + " | ".join([r.company, r.role, r.stage, r.last_action, r.next_step, r.updated]) + " |")
    return "\n".join(lines) + "\n"


def read_index(path: pathlib.Path) -> list[Row]:
    if not path.exists():
        return []
    rows: list[Row] = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        # Skip header + separator
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if cells == HEADERS or all(set(c) <= {"-", ":", " "} for c in cells):
            continue
        if len(cells) != len(HEADERS):
            continue
        rows.append(Row(*cells))
    return rows


def append_row(path: pathlib.Path, row: Row) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = read_index(path)
    rows.append(row)
    path.write_text(render_index(rows))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_add = sub.add_parser("append")
    p_add.add_argument("path", type=pathlib.Path)
    for f in fields(Row):
        p_add.add_argument(f.name)
    p_list = sub.add_parser("list")
    p_list.add_argument("path", type=pathlib.Path)

    args = parser.parse_args(argv)
    if args.cmd == "append":
        row = Row(**{f.name: getattr(args, f.name) for f in fields(Row)})
        append_row(args.path, row)
        print(render_index(read_index(args.path)), end="")
        return 0
    if args.cmd == "list":
        print(render_index(read_index(args.path)), end="")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: 4 tests pass.

- [ ] **Step 5: Remove placeholder and commit**

```bash
git rm scripts/.gitkeep
git add scripts/pipeline.py tests/test_pipeline.py
git commit -m "feat(scripts): pipeline.py — read/append applications index"
```

---

## Task 3: `fetch_jd.py` — URL → structured JD

Fetches a job description from supported ATSes (Greenhouse, Lever, Ashby) or a generic company careers page, returns structured data. Uses `beautifulsoup4` to extract title, company, location, body text. `httpx` for the HTTP.

**Files:**
- Create: `scripts/fetch_jd.py`
- Create: `tests/test_fetch_jd.py`
- Create: `tests/fixtures/jd_greenhouse.html`
- Create: `tests/fixtures/jd_lever.html`
- Create: `tests/fixtures/jd_ashby.html`

- [ ] **Step 1: Create fixture HTML files**

`tests/fixtures/jd_greenhouse.html` (minimal, just what the parser needs):

```html
<!doctype html>
<html><head><title>Product Designer at Profound</title></head>
<body>
<h1 class="app-title">Product Designer</h1>
<div class="company-name">Profound</div>
<div class="location">New York, NY</div>
<div id="content">
<p>Profound is on a mission to help companies understand AI presence.</p>
<p>Responsibilities: Design core product experiences end to end.</p>
</div>
</body></html>
```

`tests/fixtures/jd_lever.html`:

```html
<!doctype html>
<html><head><title>Senior Engineer — Example Co</title></head>
<body>
<div class="posting-headline"><h2>Senior Engineer</h2></div>
<div class="posting-categories">
  <div class="location">Remote</div>
</div>
<div class="section-wrapper">
  <div>We are looking for a senior engineer to join our team.</div>
</div>
</body></html>
```

`tests/fixtures/jd_ashby.html`:

```html
<!doctype html>
<html><head><title>Designer at Acme</title></head>
<body>
<div class="job-posting">
  <h1>Designer</h1>
  <div class="location-name">San Francisco</div>
  <div class="job-description"><p>Design great things at Acme.</p></div>
</div>
</body></html>
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_fetch_jd.py`:

```python
"""Tests for fetch_jd.py — JD HTML parsing + fetch."""
from __future__ import annotations
import pathlib

import httpx
import pytest
import respx

from fetch_jd import parse_jd, fetch_jd

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def test_parse_greenhouse():
    html = (FIXTURES / "jd_greenhouse.html").read_text()
    jd = parse_jd(html, source_url="https://boards.greenhouse.io/example/jobs/1")
    assert jd["title"] == "Product Designer"
    assert jd["company"] == "Profound"
    assert jd["location"] == "New York, NY"
    assert "AI presence" in jd["body"]
    assert jd["source"] == "greenhouse"


def test_parse_lever():
    html = (FIXTURES / "jd_lever.html").read_text()
    jd = parse_jd(html, source_url="https://jobs.lever.co/example/abc")
    assert jd["title"] == "Senior Engineer"
    assert jd["location"] == "Remote"
    assert jd["source"] == "lever"


def test_parse_ashby():
    html = (FIXTURES / "jd_ashby.html").read_text()
    jd = parse_jd(html, source_url="https://jobs.ashbyhq.com/acme/1")
    assert jd["title"] == "Designer"
    assert jd["location"] == "San Francisco"
    assert jd["source"] == "ashby"


@respx.mock
def test_fetch_jd_hits_url_and_parses():
    html = (FIXTURES / "jd_greenhouse.html").read_text()
    url = "https://boards.greenhouse.io/example/jobs/1"
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    jd = fetch_jd(url)
    assert jd["title"] == "Product Designer"
    assert jd["source_url"] == url


@respx.mock
def test_fetch_jd_raises_on_auth_wall():
    url = "https://www.linkedin.com/jobs/view/123"
    respx.get(url).mock(return_value=httpx.Response(401))
    with pytest.raises(RuntimeError, match="auth"):
        fetch_jd(url)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_fetch_jd.py -v`
Expected: ImportError — `fetch_jd` does not exist.

- [ ] **Step 4: Implement `scripts/fetch_jd.py`**

```python
#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.27",
#     "beautifulsoup4>=4.12",
# ]
# ///
"""fetch_jd.py — fetch a JD URL and parse into structured data.

Supported shapes: Greenhouse, Lever, Ashby, and a generic fallback.
LinkedIn, Workday, and other auth-walled sources are NOT supported — the
caller should prompt the user to paste the JD instead.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from typing import Any

import httpx
from bs4 import BeautifulSoup


def _detect_source(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    if "greenhouse" in host:
        return "greenhouse"
    if "lever" in host:
        return "lever"
    if "ashby" in host:
        return "ashby"
    if "linkedin" in host:
        return "linkedin"
    return "generic"


def _text(el) -> str:
    return el.get_text(strip=True) if el else ""


def parse_jd(html: str, source_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    source = _detect_source(source_url)

    if source == "greenhouse":
        title = _text(soup.select_one(".app-title, h1"))
        company = _text(soup.select_one(".company-name"))
        location = _text(soup.select_one(".location"))
        body = _text(soup.select_one("#content"))
    elif source == "lever":
        title = _text(soup.select_one(".posting-headline h2, .posting-headline h1"))
        company = ""
        location = _text(soup.select_one(".posting-categories .location, .location"))
        body = _text(soup.select_one(".section-wrapper"))
    elif source == "ashby":
        title = _text(soup.select_one(".job-posting h1, h1"))
        company = ""
        location = _text(soup.select_one(".location-name, .location"))
        body = _text(soup.select_one(".job-description"))
    else:
        title = _text(soup.select_one("h1"))
        company = ""
        location = ""
        body = _text(soup.select_one("main")) or _text(soup.select_one("body"))

    title_tag = soup.find("title")
    if title_tag and not company:
        # "Role at Company" / "Role — Company"
        text = title_tag.get_text(strip=True)
        for sep in [" at ", " — ", " - ", " | "]:
            if sep in text:
                parts = text.split(sep, 1)
                if not title:
                    title = parts[0].strip()
                company = parts[1].strip()
                break

    return {
        "title": title,
        "company": company,
        "location": location,
        "body": body,
        "source": source,
        "source_url": source_url,
    }


def fetch_jd(url: str, client: httpx.Client | None = None) -> dict[str, Any]:
    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=15.0, headers={"User-Agent": "plytools/0.1"})
    try:
        r = client.get(url)
        if r.status_code in (401, 403):
            raise RuntimeError(f"Auth wall fetching {url} (HTTP {r.status_code}) — ask user to paste the JD text instead.")
        r.raise_for_status()
        return parse_jd(r.text, source_url=url)
    finally:
        if owns_client:
            client.close()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    args = parser.parse_args(argv)
    try:
        jd = fetch_jd(args.url)
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}))
        return 2
    print(json.dumps(jd, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_fetch_jd.py -v`
Expected: 5 tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/fetch_jd.py tests/test_fetch_jd.py tests/fixtures/jd_greenhouse.html tests/fixtures/jd_lever.html tests/fixtures/jd_ashby.html
git commit -m "feat(scripts): fetch_jd.py — parse Greenhouse/Lever/Ashby JDs"
```

---

## Task 4: `resume_parse.py` — PDF → structured resume

Extracts section-level text from a resume PDF (local path or URL). Uses `pypdf` for text extraction + heuristic section detection (common headings: Experience, Education, Skills, Projects).

**Files:**
- Create: `scripts/resume_parse.py`
- Create: `tests/test_resume_parse.py`
- Create: `tests/fixtures/resume_sample.pdf` (generated at test time, see Step 1)

- [ ] **Step 1: Add a resume PDF fixture generator to `tests/conftest.py`**

We generate the fixture PDF at test time using `reportlab` (already added to dev deps in Task 1). No PDF gets committed — sidesteps the `*.pdf` gitignore rule entirely.

Modify `tests/conftest.py` — append after existing content:

```python
import pytest
from reportlab.pdfgen import canvas


@pytest.fixture
def sample_resume_pdf(tmp_path):
    """Generate a minimal resume PDF for tests."""
    path = tmp_path / "resume.pdf"
    c = canvas.Canvas(str(path))
    c.setFont("Helvetica", 12)
    y = 750
    for line in [
        "Harvey Zheng",
        "",
        "Experience",
        "Designer at Example Co (2022-2024)",
        "",
        "Education",
        "UPenn M&TSI (2018)",
        "",
        "Skills",
        "Design, Engineering, Tools",
    ]:
        c.drawString(72, y, line)
        y -= 20
    c.save()
    return path
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_resume_parse.py`:

```python
"""Tests for resume_parse.py."""
from __future__ import annotations
import httpx
import respx

from resume_parse import parse_resume_bytes, parse_resume


def test_parse_resume_bytes_extracts_sections(sample_resume_pdf):
    result = parse_resume_bytes(sample_resume_pdf.read_bytes())
    assert "Harvey Zheng" in result["raw_text"]
    assert "Experience" in result["sections"]
    assert "Education" in result["sections"]
    assert "Skills" in result["sections"]


def test_parse_resume_local_path(sample_resume_pdf):
    result = parse_resume(str(sample_resume_pdf))
    assert "Harvey Zheng" in result["raw_text"]


@respx.mock
def test_parse_resume_remote_url(sample_resume_pdf):
    url = "https://example.com/resume.pdf"
    respx.get(url).mock(return_value=httpx.Response(200, content=sample_resume_pdf.read_bytes()))
    result = parse_resume(url)
    assert "Harvey Zheng" in result["raw_text"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_resume_parse.py -v`
Expected: ImportError — `resume_parse` not yet present.

- [ ] **Step 4: Implement `scripts/resume_parse.py`**

```python
#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.27",
#     "pypdf>=4.0",
# ]
# ///
"""resume_parse.py — extract text + coarse sections from a resume PDF."""
from __future__ import annotations

import argparse
import io
import json
import pathlib
import sys
from typing import Any

import httpx
import pypdf

SECTION_HEADINGS = (
    "Experience",
    "Work Experience",
    "Employment",
    "Education",
    "Skills",
    "Projects",
    "Awards",
    "Summary",
    "Objective",
)


def _extract_text(pdf_bytes: bytes) -> str:
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    pages = [p.extract_text() or "" for p in reader.pages]
    return "\n".join(pages)


def _split_sections(text: str) -> dict[str, str]:
    """Heuristic: split into named sections based on headings on their own line."""
    lines = text.splitlines()
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        stripped = line.strip()
        matched = next((h for h in SECTION_HEADINGS if stripped.lower() == h.lower()), None)
        if matched:
            current = matched
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items() if v or k in sections}


def parse_resume_bytes(pdf_bytes: bytes) -> dict[str, Any]:
    raw = _extract_text(pdf_bytes)
    return {"raw_text": raw, "sections": _split_sections(raw)}


def parse_resume(src: str, client: httpx.Client | None = None) -> dict[str, Any]:
    if src.startswith("http://") or src.startswith("https://"):
        owns_client = client is None
        client = client or httpx.Client(follow_redirects=True, timeout=20.0)
        try:
            r = client.get(src)
            r.raise_for_status()
            return parse_resume_bytes(r.content)
        finally:
            if owns_client:
                client.close()
    path = pathlib.Path(src)
    return parse_resume_bytes(path.read_bytes())


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("src", help="URL or local path to PDF")
    args = parser.parse_args(argv)
    result = parse_resume(args.src)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_resume_parse.py -v`
Expected: 3 tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/resume_parse.py tests/test_resume_parse.py tests/conftest.py
git commit -m "feat(scripts): resume_parse.py — extract text + sections from PDFs"
```

---

## Task 5: `apollo_lookup.py` — Apollo people match + credits

**API reference (verify during implementation):** Apollo's endpoints change periodically. Before coding, confirm at https://developer.apollo.io/ that these paths + payloads still apply:
- `POST /api/v1/people/match` — body includes `first_name`, `last_name`, `organization_name` (or `domain`) and `api_key`
- `GET /api/v1/auth/health` — account / credit signal (if removed, rely on response headers like `X-Rate-Limit-Remaining` or infer via error code 402)

**Files:**
- Create: `scripts/apollo_lookup.py`
- Create: `tests/test_apollo_lookup.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_apollo_lookup.py`:

```python
"""Tests for apollo_lookup.py."""
from __future__ import annotations
import httpx
import respx

from apollo_lookup import check_credits, lookup_email


APOLLO_MATCH_URL = "https://api.apollo.io/api/v1/people/match"
APOLLO_HEALTH_URL = "https://api.apollo.io/api/v1/auth/health"


@respx.mock
def test_lookup_email_found():
    respx.post(APOLLO_MATCH_URL).mock(
        return_value=httpx.Response(200, json={
            "person": {"email": "dylan@tryprofound.com", "email_status": "verified"},
        })
    )
    result = lookup_email("Dylan", "Babbs", "tryprofound.com", api_key="k")
    assert result["email"] == "dylan@tryprofound.com"
    assert result["source"] == "apollo"
    assert result["confidence"] == "verified"


@respx.mock
def test_lookup_email_not_found_returns_null():
    respx.post(APOLLO_MATCH_URL).mock(return_value=httpx.Response(200, json={"person": None}))
    result = lookup_email("No", "One", "example.com", api_key="k")
    assert result["email"] is None
    assert result["source"] == "apollo"


@respx.mock
def test_lookup_email_out_of_credits_raises():
    respx.post(APOLLO_MATCH_URL).mock(return_value=httpx.Response(402, json={"error": "insufficient credits"}))
    try:
        lookup_email("X", "Y", "example.com", api_key="k")
    except RuntimeError as e:
        assert "credits" in str(e).lower()
    else:
        raise AssertionError("expected RuntimeError")


@respx.mock
def test_check_credits_returns_remaining():
    respx.get(APOLLO_HEALTH_URL).mock(return_value=httpx.Response(200, json={
        "is_logged_in": True,
        "credits_used": 3,
        "credits_limit": 50,
    }))
    remaining = check_credits(api_key="k")
    assert remaining == 47
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_apollo_lookup.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `scripts/apollo_lookup.py`**

```python
#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.27",
# ]
# ///
"""apollo_lookup.py — look up an email on Apollo.io and check credits."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx

APOLLO_MATCH_URL = "https://api.apollo.io/api/v1/people/match"
APOLLO_HEALTH_URL = "https://api.apollo.io/api/v1/auth/health"


def lookup_email(
    first: str,
    last: str,
    domain: str,
    api_key: str,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    owns = client is None
    client = client or httpx.Client(timeout=15.0)
    try:
        r = client.post(
            APOLLO_MATCH_URL,
            json={
                "api_key": api_key,
                "first_name": first,
                "last_name": last,
                "domain": domain,
                "reveal_personal_emails": False,
            },
        )
        if r.status_code == 402:
            raise RuntimeError("Apollo returned 402 — out of credits")
        if r.status_code == 429:
            raise RuntimeError("Apollo returned 429 — rate limited")
        if r.status_code == 401:
            raise RuntimeError("Apollo returned 401 — bad api_key")
        r.raise_for_status()
        data = r.json()
        person = data.get("person") or {}
        email = person.get("email")
        status = person.get("email_status")
        return {
            "email": email,
            "source": "apollo",
            "confidence": status or ("unknown" if email else None),
        }
    finally:
        if owns:
            client.close()


def check_credits(api_key: str, client: httpx.Client | None = None) -> int:
    """Return estimated credits remaining. Raises on auth/network errors."""
    owns = client is None
    client = client or httpx.Client(timeout=10.0)
    try:
        r = client.get(APOLLO_HEALTH_URL, params={"api_key": api_key})
        r.raise_for_status()
        data = r.json()
        used = int(data.get("credits_used", 0))
        limit = int(data.get("credits_limit", 0))
        return max(limit - used, 0)
    finally:
        if owns:
            client.close()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_lookup = sub.add_parser("lookup")
    p_lookup.add_argument("first")
    p_lookup.add_argument("last")
    p_lookup.add_argument("domain")
    sub.add_parser("credits")

    args = parser.parse_args(argv)
    api_key = os.environ.get("APOLLO_API_KEY")
    if not api_key:
        print(json.dumps({"error": "APOLLO_API_KEY not set"}))
        return 2
    try:
        if args.cmd == "lookup":
            result = lookup_email(args.first, args.last, args.domain, api_key=api_key)
        elif args.cmd == "credits":
            result = {"credits_remaining": check_credits(api_key=api_key), "source": "apollo"}
    except RuntimeError as e:
        print(json.dumps({"error": str(e), "source": "apollo"}))
        return 3
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_apollo_lookup.py -v`
Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/apollo_lookup.py tests/test_apollo_lookup.py
git commit -m "feat(scripts): apollo_lookup.py — people/match + credits"
```

---

## Task 6: `hunter_lookup.py` — Hunter email-finder + domain-search + account

Hunter's API is better documented and stable. Paths:
- `GET https://api.hunter.io/v2/email-finder` — `domain`, `first_name`, `last_name`, `api_key`
- `GET https://api.hunter.io/v2/domain-search` — `domain`, `api_key` → returns `pattern` field
- `GET https://api.hunter.io/v2/account` — `api_key` → returns usage/limits

**Files:**
- Create: `scripts/hunter_lookup.py`
- Create: `tests/test_hunter_lookup.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_hunter_lookup.py`:

```python
"""Tests for hunter_lookup.py."""
from __future__ import annotations
import httpx
import respx

from hunter_lookup import check_credits, find_pattern, lookup_email


HUNTER_FIND = "https://api.hunter.io/v2/email-finder"
HUNTER_DOMAIN = "https://api.hunter.io/v2/domain-search"
HUNTER_ACCOUNT = "https://api.hunter.io/v2/account"


@respx.mock
def test_lookup_email_found():
    respx.get(HUNTER_FIND).mock(return_value=httpx.Response(200, json={
        "data": {"email": "dylan@tryprofound.com", "score": 94, "verification": {"status": "valid"}}
    }))
    result = lookup_email("Dylan", "Babbs", "tryprofound.com", api_key="k")
    assert result["email"] == "dylan@tryprofound.com"
    assert result["source"] == "hunter"
    assert result["confidence"] in ("valid", 94, "94")


@respx.mock
def test_lookup_email_not_found():
    respx.get(HUNTER_FIND).mock(return_value=httpx.Response(200, json={"data": {"email": None, "score": 0}}))
    result = lookup_email("No", "One", "example.com", api_key="k")
    assert result["email"] is None


@respx.mock
def test_lookup_email_quota_exceeded():
    respx.get(HUNTER_FIND).mock(return_value=httpx.Response(429, json={"errors": [{"details": "Usage exceeded"}]}))
    try:
        lookup_email("X", "Y", "example.com", api_key="k")
    except RuntimeError as e:
        assert "429" in str(e) or "rate" in str(e).lower() or "quota" in str(e).lower()
    else:
        raise AssertionError("expected RuntimeError")


@respx.mock
def test_find_pattern_returns_dominant():
    respx.get(HUNTER_DOMAIN).mock(return_value=httpx.Response(200, json={
        "data": {"pattern": "{first}", "organization": "Profound"}
    }))
    pattern = find_pattern("tryprofound.com", api_key="k")
    assert pattern == "{first}"


@respx.mock
def test_check_credits_uses_account_endpoint():
    respx.get(HUNTER_ACCOUNT).mock(return_value=httpx.Response(200, json={
        "data": {"requests": {"searches": {"available": 23, "used": 2}}}
    }))
    remaining = check_credits(api_key="k")
    assert remaining == 23
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_hunter_lookup.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `scripts/hunter_lookup.py`**

```python
#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.27",
# ]
# ///
"""hunter_lookup.py — Hunter.io email-finder, domain-pattern, and account."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx

HUNTER_FIND = "https://api.hunter.io/v2/email-finder"
HUNTER_DOMAIN = "https://api.hunter.io/v2/domain-search"
HUNTER_ACCOUNT = "https://api.hunter.io/v2/account"


def _raise_on_quota(r: httpx.Response) -> None:
    if r.status_code == 401:
        raise RuntimeError("Hunter returned 401 — bad api_key")
    if r.status_code == 429:
        raise RuntimeError("Hunter returned 429 — quota exceeded")
    if r.status_code == 402:
        raise RuntimeError("Hunter returned 402 — payment required")
    r.raise_for_status()


def lookup_email(
    first: str,
    last: str,
    domain: str,
    api_key: str,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    owns = client is None
    client = client or httpx.Client(timeout=15.0)
    try:
        r = client.get(HUNTER_FIND, params={
            "domain": domain,
            "first_name": first,
            "last_name": last,
            "api_key": api_key,
        })
        _raise_on_quota(r)
        data = (r.json().get("data") or {})
        email = data.get("email")
        verification = (data.get("verification") or {}).get("status")
        confidence = verification or data.get("score") or None
        return {"email": email, "source": "hunter", "confidence": confidence}
    finally:
        if owns:
            client.close()


def find_pattern(domain: str, api_key: str, client: httpx.Client | None = None) -> str | None:
    owns = client is None
    client = client or httpx.Client(timeout=15.0)
    try:
        r = client.get(HUNTER_DOMAIN, params={"domain": domain, "api_key": api_key})
        _raise_on_quota(r)
        data = (r.json().get("data") or {})
        return data.get("pattern")
    finally:
        if owns:
            client.close()


def check_credits(api_key: str, client: httpx.Client | None = None) -> int:
    owns = client is None
    client = client or httpx.Client(timeout=10.0)
    try:
        r = client.get(HUNTER_ACCOUNT, params={"api_key": api_key})
        _raise_on_quota(r)
        data = r.json().get("data") or {}
        searches = (data.get("requests") or {}).get("searches") or {}
        return int(searches.get("available", 0))
    finally:
        if owns:
            client.close()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_lookup = sub.add_parser("lookup")
    p_lookup.add_argument("first")
    p_lookup.add_argument("last")
    p_lookup.add_argument("domain")
    p_pattern = sub.add_parser("pattern")
    p_pattern.add_argument("domain")
    sub.add_parser("credits")

    args = parser.parse_args(argv)
    api_key = os.environ.get("HUNTER_API_KEY")
    if not api_key:
        print(json.dumps({"error": "HUNTER_API_KEY not set"}))
        return 2
    try:
        if args.cmd == "lookup":
            result = lookup_email(args.first, args.last, args.domain, api_key=api_key)
        elif args.cmd == "pattern":
            result = {"pattern": find_pattern(args.domain, api_key=api_key), "source": "hunter"}
        elif args.cmd == "credits":
            result = {"credits_remaining": check_credits(api_key=api_key), "source": "hunter"}
    except RuntimeError as e:
        print(json.dumps({"error": str(e), "source": "hunter"}))
        return 3
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_hunter_lookup.py -v`
Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/hunter_lookup.py tests/test_hunter_lookup.py
git commit -m "feat(scripts): hunter_lookup.py — email-finder, pattern, account"
```

---

## Task 7: `email_fallback.py` — pattern-guess email addresses

Pure function. Applies a Hunter-style pattern (like `{first}.{last}`) to a name + domain to produce a candidate email. No network.

**Files:**
- Create: `scripts/email_fallback.py`
- Create: `tests/test_email_fallback.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_email_fallback.py`:

```python
"""Tests for email_fallback.py — pattern-guess emails."""
from __future__ import annotations

from email_fallback import apply_pattern


def test_apply_pattern_first():
    assert apply_pattern("Dylan", "Babbs", "tryprofound.com", "{first}") == "dylan@tryprofound.com"


def test_apply_pattern_first_dot_last():
    assert apply_pattern("Dylan", "Babbs", "tryprofound.com", "{first}.{last}") == "dylan.babbs@tryprofound.com"


def test_apply_pattern_first_initial_last():
    assert apply_pattern("Dylan", "Babbs", "tryprofound.com", "{f}{last}") == "dbabbs@tryprofound.com"


def test_apply_pattern_last_first_initial():
    assert apply_pattern("Dylan", "Babbs", "tryprofound.com", "{last}{f}") == "babbsd@tryprofound.com"


def test_apply_pattern_handles_mixed_case_and_trims():
    assert apply_pattern("  DYLAN ", "babbs", "TRYPROFOUND.com", "{first}.{last}") == "dylan.babbs@tryprofound.com"


def test_apply_pattern_unknown_token_raises():
    import pytest
    with pytest.raises(ValueError, match="unknown"):
        apply_pattern("A", "B", "example.com", "{middle}")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_email_fallback.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `scripts/email_fallback.py`**

```python
#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# ///
"""email_fallback.py — apply a Hunter-style pattern to a name + domain."""
from __future__ import annotations

import argparse
import json
import re
import sys

_VALID_TOKENS = {"first", "last", "f", "l"}


def apply_pattern(first: str, last: str, domain: str, pattern: str) -> str:
    first = first.strip().lower()
    last = last.strip().lower()
    domain = domain.strip().lower()

    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if token == "first":
            return first
        if token == "last":
            return last
        if token == "f":
            return first[:1]
        if token == "l":
            return last[:1]
        raise ValueError(f"unknown token in pattern: {{{token}}}")

    local = re.sub(r"\{([a-z]+)\}", replace, pattern)
    return f"{local}@{domain}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("first")
    parser.add_argument("last")
    parser.add_argument("domain")
    parser.add_argument("pattern")
    args = parser.parse_args(argv)
    try:
        email = apply_pattern(args.first, args.last, args.domain, args.pattern)
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        return 2
    print(json.dumps({"email": email, "source": "pattern", "confidence": "guessed"}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_email_fallback.py -v`
Expected: 6 tests pass.

- [ ] **Step 5: Run full test suite to confirm no regressions**

Run: `uv run pytest -v`
Expected: all tests across all files pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/email_fallback.py tests/test_email_fallback.py
git commit -m "feat(scripts): email_fallback.py — pattern-based email guessing"
```

---

## Task 8: Draft templates (shared prompt + 4 personas)

Markdown files only. No tests — these are prompts the LLM consumes, not code.

**Files:**
- Create: `templates/prompt.md`
- Create: `templates/warm_intro_ask.md`
- Create: `templates/cold_hiring_manager.md`
- Create: `templates/cold_exec.md`
- Create: `templates/cold_peer.md`

- [ ] **Step 1: Create `templates/prompt.md` (shared rules)**

```markdown
# Shared drafting rules

These rules apply to **every** outreach draft generated by the job-apply skill.
Per-persona templates in this directory layer persona-specific rules on top.

## Never

- Never open with "I hope this finds you well" or any generic pleasantry.
- Never use filler: "passionate", "synergy", "rock star", "ninja", "guru".
- Never mention salary, compensation, or benefits in a first-touch email.
- Never claim generic fit ("I'd be a great addition to your team") — always point to a specific thing.
- Never ask for an interview directly in a cold email. Ask for a conversation or a quick chat.

## Always

- Always include a link to harveyzheng.com somewhere.
- Always match at least ONE concrete thing to the JD: a project, a tool, a phrase from the description.
- Always keep subject lines under 50 characters and specific to the role.
- Always sign off with first name only.
- Always leave the reader with a low-friction next step (15-min chat, or "happy to send a Loom walkthrough").

## Tone

Crisp, specific, no corporate fluff. First person. Skim-friendly.
Lowercase-ish when the persona warrants it (warm intros, peers). Sentence case elsewhere.

## Structure hints

- Paragraphs are short (1–3 sentences). White space is a feature.
- One idea per paragraph.
- Put links inline, not at the end, when they reinforce a claim.

## When positioning.md sets overrides

If `~/.claude/projects/-Users-harvey-Development-plytools/memory/positioning.md`
contains additional Never/Always/Tone rules, honor those IN ADDITION to these.
User-set rules win on any conflict.
```

- [ ] **Step 2: Create `templates/warm_intro_ask.md`**

```markdown
---
persona: warm-intro
length: 60-90 words
tone: casual, warm, direct
---

# Intent
Ask a personal contact for an intro to the hiring manager or a relevant person
at their company. Make it easy for them to forward.

# Rules
- Subject: "Intro to {Company} {team}?" — under 50 chars.
- Open: acknowledge the relationship (don't be weirdly formal).
- Middle: one-liner on why the role fits (specific, pulled from positioning.md).
- Offer to send a tailored outreach they can forward.
- Close: a direct yes/no ask.

# Structure
Hey {name} — (hook, relationship-aware) → one-line fit → offer to send a forwardable → direct ask → sign-off.

# Example (not to copy verbatim)

> Subject: Intro to Profound design team?
>
> Hey Praneeth — saw Profound's hiring a Product Designer and the JD reads
> like it was written for me (design + prototype in code + ship to prod).
> [one specific project matched to the JD]. Would you be open to intro-ing
> me to the hiring manager or Head of Design?
>
> Happy to send a short tailored outreach you can just forward. Portfolio: harveyzheng.com.
>
> — Harvey
```

- [ ] **Step 3: Create `templates/cold_hiring_manager.md`**

```markdown
---
persona: hiring-manager
length: 80-120 words
tone: crisp, specific, no corporate fluff
---

# Intent
Land a reply. Not a full pitch — enough to make them want to see more.
Target: the role owner (Head of Design for a design role, even if the JD
is signed by a different person).

# Rules
- Subject: under 50 chars, specific to this role.
- Open: lead with why you're writing *this* person about *this* role — not "saw your posting".
- Middle: ONE concrete project/skill matched to their JD, linked inline.
- Close: low-friction CTA (15-min chat, or "happy to send a Loom walkthrough").

# Structure
Hook (1 line, role-specific) → Fit (2 lines, 1 specific project) → CTA (1 line) → Sign-off + portfolio link.

# Variant guidance
- v1 (portfolio-led): lead with the project, use unicorn framing as the bonus line.
- v2 (unicorn-led): open with the designer+engineer hybrid angle, project supports it.
```

- [ ] **Step 4: Create `templates/cold_exec.md`**

```markdown
---
persona: exec
length: 70-110 words
tone: terse, outcome-focused, respectful of their time
---

# Intent
Cold email to a CTO, founder, or other exec. They skim; get to the point.

# Rules
- Subject: outcome-focused, under 40 chars.
- Open: reason you're writing them specifically (public post, JD signature, past thing they shipped).
- Middle: the engineering-side of Harvey — shipping code to prod, prototyping, git workflow.
  Design is the "also, I can own the visual side end-to-end" bonus.
- Close: specific, low-cost ask ("15 min next week?"). No "let me know your thoughts".

# Structure
Hook (1 line) → Shipping fit (1-2 lines) → Design-also (1 line) → CTA (1 line) → Sign-off + link.

# Variant guidance
- v1 (ship-led): concrete shipped work, commit history, prod experience.
- v2 (systems-led): technical breadth, infra/tooling, design-system work.
```

- [ ] **Step 5: Create `templates/cold_peer.md`**

```markdown
---
persona: peer
length: 50-80 words
tone: casual, curious, no-ask
---

# Intent
Say hi to a same-function peer at the target company. Signal interest, sample
the culture. NOT a reach-out about the job directly. Zero asks.

# Rules
- Subject: reference a specific thing they shipped or wrote.
- Open: "saw [specific thing], [specific reaction]."
- Middle: a one-liner about what you're working on that connects.
- Close: "anyway, nice work" / "hope that's useful" — no ask, no CTA.

# Structure
Hook (specific thing they did) → connection (1 line) → soft-sign-off + link.

# Variant guidance
- v1 (their work): lead with a thing they made.
- v2 (shared interest): lead with a tool/framework/design system you both care about.
```

- [ ] **Step 6: Commit**

```bash
git add templates/
git commit -m "feat(templates): shared prompt + 4 persona drafting templates"
```

---

## Task 9: Schema examples (`schemas/*.example.md`)

Adopter-facing examples using fake data. No tests.

**Files:**
- Create: `schemas/profile.example.md`
- Create: `schemas/positioning.example.md`
- Create: `schemas/contacts.example.md`

- [ ] **Step 1: Create `schemas/profile.example.md`**

```markdown
---
name: Profile — experience & work
description: Structured experience/projects/skills from your resume and portfolio
type: user
---

# Profile (example — replace with your own)

## Experience
- Senior Designer at Example Co (2022–2024) — shipped X; led Y; impact Z
- Designer at Acme (2020–2022) — designed feature A; improved metric B by C%

## Projects (portfolio highlights)
- Example Dashboard — data-viz for B2B marketers; live at https://example.com/dashboard; tags: design, data-viz, react
- Acme Design System — 40+ components, adopted across 3 teams; tags: design-systems, tokens

## Skills
Design: Figma, Framer, motion, design systems, data visualization
Engineering: TypeScript, React, Next.js, Tailwind, git
Tools: v0, Cursor, Linear, Figma plugins
```

- [ ] **Step 2: Create `schemas/positioning.example.md`**

```markdown
---
name: Positioning — how to pitch me
description: Framing rules, tone preferences, and angles to emphasize per role type
type: user
---

# Positioning (example — replace with your own)

## The pitch (one-liner)
"Designer+engineer hybrid — I prototype in code and ship to prod."

## Angles by role type
- Design-led role → foreground craft; hybrid framing as bonus, not lede
- Eng-led role → foreground shipping; design as "also"
- Founding / generalist → lead with hybrid framing from line 1

## Tone
Crisp, specific, no corporate fluff. First person. Skim-friendly.

## Always include
- Link to my portfolio (https://example.com)
- One concrete project matched to the JD

## Never (additional to templates/prompt.md)
- Never describe myself as "a designer who codes" — prefer "designer + engineer hybrid"

## Portfolio source (optional)
# If your portfolio lives in a local git repo, set local_path to read from disk
# (richer signal than scraping the live site).
# local_path: /path/to/your/portfolio/repo
url: https://example.com
```

- [ ] **Step 3: Create `schemas/contacts.example.md`**

```markdown
---
name: Personal contacts
description: People I know personally who could provide warm intros
type: reference
---

# Contacts (example — replace with your own)

| Name | Current company | Relationship | Last contact | Notes |
|------|-----------------|--------------|--------------|-------|
| Example Name | ExampleCo | Ex-coworker (2020-2022) | 2026-01 | Slack DM open; happy to refer |
| Another Person | AcmeCorp | Summer-camp 2018 | 2026-03 | LinkedIn connected; prefer texting |
```

- [ ] **Step 4: Commit**

```bash
git add schemas/
git commit -m "docs(schemas): profile, positioning, contacts example schemas"
```

---

## Task 10: `skills/job-apply/SKILL.md` — the orchestrator

The Skill file. Frontmatter drives discovery; body describes the six-stage workflow, HITL gates, script invocations, and data paths.

**Files:**
- Create: `skills/job-apply/SKILL.md`

- [ ] **Step 1: Create `skills/job-apply/SKILL.md`**

```markdown
---
name: job-apply
description: End-to-end job-application outreach. Use when the user pastes a JD URL, mentions applying to a company, asks for outreach drafts, or says things like "help me reach out to [company]", "draft an email to the hiring manager at [company]", or "apply to this role". Orchestrates six stages — profile intake, JD ingest, LinkedIn contact filtering, HITL target selection, email discovery via Apollo/Hunter/pattern-guess, persona-tuned draft generation, and pipeline logging — with user data isolated in auto-memory and tool code in this repo.
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
   - On quota/error, skip to pattern-guess.
3. **Pattern-guess** — `uv run scripts/hunter_lookup.py pattern <domain>` to
   get the dominant pattern, then `uv run scripts/email_fallback.py <first>
   <last> <domain> <pattern>`. Flag as `confidence: guessed`.
4. **Manual** — print a copy-paste block:
   - Apollo web UI search link: `https://app.apollo.io/#/people?qKeywords=<name>&qOrganizationName=<company>`
   - Hunter web UI: `https://hunter.io/search/<domain>`
   - LinkedIn Sales Nav hint
   - Common patterns to try ({first}, {first}.{last}, {f}{last})

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
Increment by 1 per successful Apollo or Hunter lookup call (not pattern-guess,
not manual). Before every lookup:

- If `credits_used_this_session >= 10`: **stop**, show the counter, ask the
  user whether to continue. Only proceed on explicit approval.

## Environment variables

Read `.env` at the repo root (if present). Expected:
- `APOLLO_API_KEY` — required for Apollo cascade step
- `HUNTER_API_KEY` — required for Hunter + pattern-guess steps

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
- Never exceed the 10-credit session cap without explicit user approval.
```

- [ ] **Step 2: Commit**

```bash
git add skills/job-apply/SKILL.md
git commit -m "feat(skill): job-apply orchestrator SKILL.md"
```

---

## Task 11: `README.md` — adopter-facing docs

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create `README.md`**

```markdown
# plytools

A Claude Code skill + helper scripts for running job-application outreach
end-to-end: JD ingest → LinkedIn contact tiering → email discovery (Apollo →
Hunter → pattern-guess → manual) → persona-tuned draft generation → pipeline
logging.

## How it works

The skill at `skills/job-apply/` orchestrates a six-stage workflow. Judgment
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

3. Copy `.env.example` to `.env` and fill in API keys you have:

   ```bash
   cp .env.example .env
   # edit .env
   ```

   - Apollo: https://developer.apollo.io/ (paid tier for API)
   - Hunter: https://hunter.io/api (free tier available)

   Both are optional. The skill falls through the cascade and lands on manual
   instructions if no keys are set.

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

## Running scripts directly

Each script in `scripts/` is a standalone `uv` script:

```bash
uv run scripts/fetch_jd.py https://boards.greenhouse.io/example/jobs/1
uv run scripts/apollo_lookup.py lookup Dylan Babbs tryprofound.com
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

Built with Claude Code. See `docs/superpowers/specs/` and `docs/superpowers/plans/`.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with setup, usage, and safety notes"
```

---

## Task 12: End-to-end smoke test

Not an automated test — a manual walkthrough that confirms each stage hangs
together. Done once after everything above is merged.

**Files:**
- None created. Human-in-the-loop verification.

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: all tests across all `tests/*.py` files pass.

- [ ] **Step 2: Verify each script is directly runnable**

```bash
uv run scripts/pipeline.py list /tmp/nonexistent.md                    # should print empty table header
uv run scripts/email_fallback.py Dylan Babbs tryprofound.com "{first}"  # should print {"email":"dylan@tryprofound.com",...}
```

Expected: both commands exit 0 with JSON/markdown output on stdout.

- [ ] **Step 3: Verify gitignore catches sensitive paths**

```bash
mkdir -p applications/Test memory
echo "fake" > applications/Test/contacts.md
echo "fake" > memory/profile.md
touch .env
git status --short
```

Expected: none of `.env`, `applications/`, or `memory/` appear as untracked.
Cleanup afterwards: `rm -rf applications memory .env`.

- [ ] **Step 4: Invoke the skill in Claude Code**

Open this repo in Claude Code. Type:

> "Help me apply to this role: [paste a public JD URL such as the Profound
> Product Designer role if still live, or any Greenhouse posting]"

Expected walkthrough:
1. Skill runs Stage 0 intake (if `profile.md` not in auto-memory yet).
2. Skill runs Stage 1 — fetches the JD, writes `jd.md` to auto-memory.
3. Skill asks for pasted LinkedIn contacts.
4. Skill runs Stage 2 — prints tiered list with "why" lines.
5. Skill pauses at Stage 2.5 HITL gate — **does not** auto-pick anyone.
6. User picks targets.
7. Skill runs Stage 3 cascade. Credits counter visible; hard-stops at 10.
8. Skill runs Stage 4 — writes v1/v2 drafts per target.
9. Skill runs Stage 5 — appends to `applications/index.md`.

If any stage behaves unexpectedly, file an issue describing the deviation.

- [ ] **Step 5: No commit needed** — this task just validates the built system.

---

## Self-review coverage map

| Spec section | Task(s) |
|--------------|---------|
| Repo layout | 1, 8, 9, 10, 11 |
| User-data layout | 10 (SKILL.md documents), 12 (gitignore verification) |
| Stage 0 intake | 10 |
| Stage 1 JD ingest | 3 (script), 10 (orchestration) |
| Stage 2 contact filter | 10 (judgment lives in SKILL) |
| Stage 2.5 HITL gate | 10 |
| Stage 3 email cascade | 5, 6, 7 (scripts), 10 (orchestration) |
| Stage 4 draft generation | 8 (templates), 10 (orchestration) |
| Stage 5 pipeline update | 2 (script), 10 (orchestration) |
| Memory schemas | 9 (examples), 10 (references in SKILL) |
| Templates | 8 |
| Error handling | 3–7 (per script), 10 (surfacing) |
| Testing | 2–7 (unit tests), 12 (integration) |
| Open-source safety | 1 (gitignore), 11 (README), 12 (verification) |
| Invocation | 10 (SKILL frontmatter) |
| Dependencies | 1 (pyproject.toml) |

All spec sections have at least one task. No gaps.
