# Migration validation - 2026-09-07

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
