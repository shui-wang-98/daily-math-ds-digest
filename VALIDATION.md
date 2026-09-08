# HTML-only daily output validation - 2026-09-08

New daily finalization generates HTML and backend JSON only. Historical PDF and
Markdown files remain unchanged, and secondary links are discovered from files
that actually exist. The dated HTML URL remains the primary report URL.

## Current results

- Initial working tree: clean.
- Exact test command: `.\.venv\Scripts\python.exe -m pytest -q`.
- Exact final result: **62 passed in 5.49s** (exit code 0).
- `git diff --check`: passed; Git emitted LF-to-CRLF conversion advisories.
- Offline normal date `2026-09-04`: three papers, one in each priority class.
- Offline empty date `2026-09-05`: zero papers, correct no-new-papers page.
- Both new dated directories contain exactly `index.html` and `report.json`;
  no local digest PDF or Markdown files were generated anywhere in the demo site.
- Verified all archive dates newest first, counts, relative links, matching
  data/published JSON, full HIGH/RELATED fields and original abstracts, abbreviated
  LOW entries, external arXiv paper PDF links, and exclusion of replacement-only
  submissions. The state contains exactly the three eligible fixture IDs.
- Repeated finalization and HTML rebuilding retain identical bytes and timestamps.
- Tests cover existing legacy files during same-date retry, a later new date,
  and HTML rebuilding; neither bytes nor timestamps change. Mixed archives keep
  legacy secondary links and omit them for HTML-only dates. Empty files and
  directories are excluded from download discovery, and filenames are URL-encoded.
- Tests cover validation, HTML/JSON/index rendering and promotion failures,
  delayed state writes, recovery, same-day merging, and no-new-papers idempotency.
- Notifications validate HTML and matching JSON without requiring downloads;
  generated notification text links to dated HTML and the permanent archive.
  Notification tests use mocks. No actual notification was sent.
- Browser inspection: homepage, full normal report, native abstract expansion,
  and no-new-papers page at desktop and mobile width (390px). No horizontal
  overflow or browser console errors. The existing design, external paper links,
  mathematical rendering, and print CSS are retained.
- All 14 protected production files retain identical SHA-256 hashes and
  modification timestamps. This includes production state, every historical
  site artifact (HTML, PDF, Markdown, JSON, homepage and assets), report metadata,
  profile configuration, fetching code, schema/models, and workflow. No production
  historical report was regenerated during this change.
- `requirements.txt`: removed ReportLab and pypdf. Matplotlib and pylatexenc
  remain necessary for vector mathematics and author accents. No new dependency.
- `.github/workflows/daily.yml`: unchanged; it already only deploys committed
  files and calls the notifier, with no direct PDF/Markdown assumption.
- No unresolved implementation issue. Browser Save-as-PDF pagination was not
  re-tested; print CSS is unchanged. Live deployment/notification was not run.
- No commit, push, deployment, notification, API key, paid service, or scheduled-task
  change. All demonstration output is isolated under ignored `tmp/`.

## Exact future generated output set

```text
data/state.json
data/reports/YYYY-MM-DD.json
site/index.html
site/reports/YYYY-MM-DD/index.html
site/reports/YYYY-MM-DD/report.json
site/assets/style.css
site/.nojekyll
```

The last two shared assets are written only when needed or changed. The separate
preparation/analysis steps still use ignored pending/analysis JSON. Existing
legacy PDF and Markdown files are preserved in place, never regenerated.

## Exact offline demonstration commands

Run from the repository root with a fresh `tmp/html-only-demo/` directory:

```powershell
.\.venv\Scripts\python.exe -m src.prepare_run --local-feed tests/fixtures/math_ds.xml --report-date 2026-09-04 --data-dir tmp/html-only-demo/data
Copy-Item -LiteralPath tests/fixtures/analysis_run.json -Destination tmp/html-only-demo/data/analysis_run.json
.\.venv\Scripts\python.exe -m src.finalize_run --analysis tmp/html-only-demo/data/analysis_run.json --data-dir tmp/html-only-demo/data --site-dir tmp/html-only-demo/site
.\.venv\Scripts\python.exe -m src.prepare_run --local-feed tests/fixtures/math_ds.xml --report-date 2026-09-05 --data-dir tmp/html-only-demo/data
@'
from src.models import AnalysisRun
from src.utils import atomic_write_json
atomic_write_json('tmp/html-only-demo/data/analysis_run.json', AnalysisRun(report_date='2026-09-05', overview='No new papers.', papers=[]))
'@ | .\.venv\Scripts\python.exe -
.\.venv\Scripts\python.exe -m src.finalize_run --analysis tmp/html-only-demo/data/analysis_run.json --data-dir tmp/html-only-demo/data --site-dir tmp/html-only-demo/site
.\.venv\Scripts\python.exe -m src.notify --check-only --data-dir tmp/html-only-demo/data --site-dir tmp/html-only-demo/site
.\.venv\Scripts\python.exe -m src.rebuild_site --data-dir tmp/html-only-demo/data --site-dir tmp/html-only-demo/site
```

An additional read-only audit checked the exact output sets, local links, count
metadata, all full/compact fields, state IDs, and production hashes. It repeated
`finalize_run` and `rebuild_site` with the same demo paths and verified identical
bytes and timestamps for every demo file.

## Files in this change

Added: no tracked files. Ignored demonstration and audit files are under `tmp/`.

Changed:

- `AGENTS.md`, `DAILY_AUTOMATION.md`, `README.md`, `SETUP_CHECKLIST.zh-CN.md`,
  `VALIDATION.md`
- `requirements.txt`
- `src/finalize_run.py`, `src/math_render.py`, `src/notify.py`,
  `src/rebuild_site.py`, `src/report.py`
- `templates/index.html.j2`, `templates/report.html.j2`
- `tests/conftest.py`, `tests/test_html_archive.py`, `tests/test_math_render.py`,
  `tests/test_notify.py`, `tests/test_pipeline.py`, `tests/test_render.py`

Removed: `templates/report.md.j2` and the unused `templates/email.html.j2`.
Obsolete PDF generation and Markdown formatting code was removed from the retained
renderer modules. No generated historical file or Markdown documentation was removed.

---

# Historical migration validation - 2026-09-07

The record below describes the earlier multi-format pipeline before the HTML-only
change above; its PDF/Markdown generation expectations are no longer current.

The local Codex task now prepares RSS metadata, writes structured analysis,
and finalizes HTML/PDF/Markdown/JSON locally. GitHub Actions only checks committed
artifacts, deploys Pages, and posts/updates the persistent Issue notification.
There is no model API dependency or direct email sender.

## Results

- Dependency installation: `python -m pip install -r requirements.txt` succeeded
  in the repository-local `.venv` using Python 3.12.14. The first sandboxed
  download failed; the approved network retry succeeded. The bundled Python
  executable was used to create the environment because `python` was initially
  absent from PATH. No system Python installation was changed.
- Final test command: `pytest -q`.
- Exact final test result: **44 passed in 9.82s** (exit code 0).
- `git diff --check`: passed.
- Fixture demonstration: three unseen papers, one in each priority, all expected
  artifacts generated; `src.notify --check-only` passed.
- Repeated finalization: tests verify identical file bytes and modification
  times, including the PDF, JSON, index, and state. Damaged artifacts are repaired.
- Failure tests: invalid analysis, PDF rendering, index rendering, publication,
  and state-write failures; state never marks papers seen before outputs succeed.
- RSS tests: new/cross/replace-cross, exclusion of replacement-only entries,
  normalized identifiers, duplicate feed entries, malformed entries, preservation
  of mathematical inequalities, and preparation without state changes.
- Schema tests: required fields, priorities, confidence, dates, missing/extra/
  duplicate IDs, normalized duplicate IDs, and schema-export consistency.
- No-new-papers, same-day additions, same-day empty reruns, stale pending runs,
  and offline subprocess command execution are tested.
- Notifications: mocked Issue creation, pagination beyond 100 items, comment
  updates, duplicate suppression, Pages subpath links, and incomplete-report
  rejection. No actual Issue or message was sent.
- Inspected complete generated JSON and Markdown; viewed HTML report and index
  in the browser; rendered and visually checked both final PDF pages. Repaired
  orphaned PDF headings and Markdown spacing while preserving the report design.
- The research profile is semantically identical to the original `config.yaml`.
  Production `data/state.json` is unchanged. The email template remains available.
- No commit, push, new secret, scheduled task, Pages deployment, or live arXiv
  fetch was performed. Live GitHub deployment/notification remains untested until
  a future authorized push. The future schedule remains deferred as requested.

## Exact offline demonstration commands

From the repository root, the local virtual environment was placed on PATH:

```powershell
$env:PATH = (Join-Path (Get-Location) '.venv\Scripts') + ';' + $env:PATH
python -m src.prepare_run --local-feed tests/fixtures/math_ds.xml --report-date 2026-09-04 --data-dir tmp/offline-demo/data
Copy-Item tests/fixtures/analysis_run.json tmp/offline-demo/data/analysis_run.json
python -m src.finalize_run --analysis tmp/offline-demo/data/analysis_run.json --data-dir tmp/offline-demo/data --site-dir tmp/offline-demo/site
python -m src.notify --check-only --data-dir tmp/offline-demo/data --site-dir tmp/offline-demo/site
python -m src.finalize_run --analysis tmp/offline-demo/data/analysis_run.json --data-dir tmp/offline-demo/data --site-dir tmp/offline-demo/site
```

Finalization was rerun after the visual formatting fixes. The sample PDF is
`tmp/offline-demo/site/reports/2026-09-04/math-DS-digest-2026-09-04.pdf`.
Demo output is ignored and isolated from real report state and publication.
The synthetic fixture analysis must never be used as a live report.
For another complete demonstration, use a fresh demo directory; an existing
demo state's seen IDs will correctly be excluded by a new preparation.

## Files added

- `AGENTS.md`
- `DAILY_AUTOMATION.md`
- `VALIDATION.md`
- `pytest.ini`
- `schemas/analysis_run.schema.json`
- `src/prepare_run.py`
- `src/finalize_run.py`
- `tests/conftest.py`
- `tests/fixtures/analysis_run.json`
- `tests/test_notify.py`
- `tests/test_pipeline.py`

## Files changed

- `.github/workflows/daily.yml`
- `.gitignore`
- `README.md`
- `SETUP_CHECKLIST.zh-CN.md`
- `config.yaml`
- `prompts/daily_overview.txt`
- `prompts/paper_analysis.txt`
- `requirements.txt`
- `site/index.html`
- `src/config.py`
- `src/fetch_arxiv.py`
- `src/models.py`
- `src/notify.py`
- `src/report.py`
- `src/utils.py`
- `templates/paper_card.html.j2`
- `templates/report.html.j2`
- `templates/report.md.j2`
- `tests/fixtures/math_ds.xml`
- `tests/test_fetch_arxiv.py`
- `tests/test_render.py`

## Files removed

- `src/ai.py` - model API and fallback analysis implementation.
- `src/main.py` - obsolete one-step API-based pipeline.
- `.env.example` - obsolete AI and email credential examples.

Ignored local outputs also include `.venv/` and `tmp/` (package cache, test
artifacts, the isolated demonstration, and PDF inspection images).

## Remaining decisions

No unresolved implementation decision. The user will review and commit/push
the migration when ready, enable Pages/Issues if needed, and configure the
Monday-Friday 11:00 Europe/Warsaw task later in the desktop app.
Complex mathematical PDF notation still requires per-report review because the
preserved ReportLab renderer converts LaTeX to text rather than typesetting TeX.
