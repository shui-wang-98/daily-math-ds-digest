# Daily math.DS Digest

A personalized, English-only research digest from the official arXiv math.DS RSS feed. Codex in the desktop app reads the titles and abstracts and writes the analysis. The Python code fetches metadata, validates that analysis, and renders the reports locally.

**No OpenAI API key, OpenAI Python SDK, OpenAI API billing, or other paid AI API is required.** The local scripts never call a model. Codex uses your existing ChatGPT sign-in and applicable account usage limits; this does not imply an unlimited or free Codex subscription.

```text
local Codex scheduled task
    -> python -m src.prepare_run
    -> Codex writes data/analysis_run.json
    -> python -m src.finalize_run --analysis data/analysis_run.json
    -> HTML / PDF / Markdown / JSON and site index
    -> validation, inspection, git commit and push
    -> GitHub Actions deploys committed site/ and posts an Issue notification
```

## Local setup

Use Python 3.12 or newer and an existing Git checkout. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
pytest -q
```

On macOS/Linux activate with `source .venv/bin/activate`. If PowerShell blocks activation, use `.venv\Scripts\python.exe` and `.venv\Scripts\pytest.exe` directly. No `.env` file or user-created secret is needed. The `tzdata` dependency supplies timezone data on Windows.

The future schedule is **Monday-Friday at 11:00 Europe/Warsaw**, respecting daylight saving time. **The schedule will be configured later in the desktop app; this repository does not create it.** Select this local project and use the instructions in [DAILY_AUTOMATION.md](DAILY_AUTOMATION.md).

For local scheduled tasks, the computer must be on, awake, connected to the internet, and the ChatGPT/Codex desktop app must be running at the scheduled time. The project must remain available on disk. See the [official scheduled-task documentation](https://learn.chatgpt.com/docs/automations?surface=app).

## Preparation and analysis

```powershell
python -m src.prepare_run
```

Preparation fetches `https://rss.arxiv.org/rss/math.DS`. It includes `new`, `cross`, and `replace-cross`, excludes replacement-only entries, normalizes versioned arXiv IDs, and compares them with `data/state.json`. Duplicate feed IDs are collapsed. A malformed feed fails without silently dropping papers.

It atomically writes `data/pending_run.json`: report date, preparation time, feed build time, category, a snapshot of the research profile, and every unseen paper's title, authors, original abstract, categories, announcement type, IDs, arXiv URL (`abstract_url`), and PDF URL. It never changes state or marks papers seen.

The default report date is the **run date in Europe/Warsaw**, even for a stale feed. `--report-date YYYY-MM-DD` provides an explicit date for a fixture or a deliberate backfill. `--local-feed PATH` reads local XML without a network request. `--data-dir PATH` isolates preparation state and pending data for demonstrations.

Codex must read [config.yaml](config.yaml), the pending file, and [DAILY_AUTOMATION.md](DAILY_AUTOMATION.md), then write `data/analysis_run.json`. There is no automatic keyword fallback. The authoritative Pydantic schema is in [src/models.py](src/models.py); its machine-readable export is [schemas/analysis_run.schema.json](schemas/analysis_run.schema.json).

The top-level keys are `report_date`, `overview`, and `papers`. Every paper entry must explicitly contain:

| Field | Type / allowed values |
| --- | --- |
| `arxiv_id` | arXiv identifier; normalized before matching |
| `priority` | `HIGH PRIORITY`, `RELATED / POSSIBLY INTERESTING`, or `LOW PRIORITY` |
| `confidence` | `high`, `medium`, or `low` |
| `relevance_note`, `tldr`, `problem`, `main_result`, `context` | strings |
| `methods`, `prerequisites`, `keywords` | lists of strings |

Unknown fields, missing fields, duplicate IDs (including version aliases), invalid priorities/confidences/dates, missing papers, unexpected papers, and mismatched report dates are rejected. Full digest text must be nonempty. Use **“Not specified in the abstract.”** for unsupported information. Low-priority entries still require every field; use empty digest strings and lists, with a short relevance note. Their rendered cards contain only title, authors, and arXiv identifier. High-priority and related entries retain the full English digest and original abstract.

For no unseen papers, supply the pending date, an overview such as `No new papers.`, and `"papers": []`. Finalization produces the same report formats. A same-day rerun preserves an existing nonempty report instead of erasing it.

## Finalization, recovery, and output

```powershell
python -m src.finalize_run --analysis data/analysis_run.json
pytest -q
python -m src.notify --check-only
```

Finalization validates before writing, merges analysis with the original metadata, and stages all rendering and the updated index inside the data directory. It produces:

```text
data/reports/YYYY-MM-DD.json
site/reports/YYYY-MM-DD/index.html
site/reports/YYYY-MM-DD/math-DS-digest-YYYY-MM-DD.pdf
site/reports/YYYY-MM-DD/math-DS-digest-YYYY-MM-DD.md
site/reports/YYYY-MM-DD/report.json
site/index.html
site/assets/style.css
site/.nojekyll
data/state.json
```

State is updated **only after** every report and index file has been generated and promoted successfully. Rendering/index failures leave the archive and state intact. File replacement is atomic individually; a filesystem failure during promotion can leave some files updated, but leaves state unadvanced. Keep the pending and analysis files and rerun the same finalizer to recover. Do not prepare a different run while recovering. Run one preparation/analysis/finalization sequence at a time.

Identical finalization preserves timestamps and file bytes, including the PDF and state. Missing report artifacts are regenerated. New papers found later on the same date are merged into that day's report; write the overview for the combined report after reading the existing report's titles/abstracts. Pending papers already recorded for a different date are rejected as stale.

The PDF retains the existing ReportLab layout and converts LaTeX to readable text; it is not a full TeX typesetter. Prefer formula-free English when it preserves the abstract's meaning. Inspect formula-rich PDFs for loss of mathematical notation before publishing. HTML supports MathJax, which loads from a public CDN when viewed; the Python tests and PDF generation are offline.

`data/pending_run.json`, `data/analysis_run.json`, `.venv/`, and `tmp/` are local and ignored. Keep `data/state.json`, `data/reports/`, and `site/` under version control. Research preferences and templates are preserved.

## Fully offline demonstration

The fixture papers are synthetic. Run these commands from the repository root with the virtual environment active; all demo state and generated files remain under ignored `tmp/offline-demo/`:

```powershell
python -m src.prepare_run --local-feed tests/fixtures/math_ds.xml --report-date 2026-09-04 --data-dir tmp/offline-demo/data
Copy-Item tests/fixtures/analysis_run.json tmp/offline-demo/data/analysis_run.json
python -m src.finalize_run --analysis tmp/offline-demo/data/analysis_run.json --data-dir tmp/offline-demo/data --site-dir tmp/offline-demo/site
python -m src.notify --check-only --data-dir tmp/offline-demo/data --site-dir tmp/offline-demo/site
python -m src.finalize_run --analysis tmp/offline-demo/data/analysis_run.json --data-dir tmp/offline-demo/data --site-dir tmp/offline-demo/site
```

The last command checks the normal rerun path. The fixture analysis is hand-authored for testing and must never be copied into a live digest. The test suite blocks HTTP requests, exercises the fixture and all three priority sections, checks output text/PDFs, and simulates rendering, publication, and state-write failures.

Start preparation with a fresh demo data directory. If this demonstration already
ran, rerun only the finalizer, or choose a different empty demo directory in both
commands: its existing state correctly excludes papers that were already finalized.

## GitHub publication and notifications

When you are ready, review and commit the repository changes yourself. This migration does not commit, push, or create a scheduled task.

In GitHub, enable Issues and select **Settings > Pages > Build and deployment > Source > GitHub Actions**. Use existing local Git authentication for future pushes. No email credentials, AI credentials, or custom Actions secret is required. GitHub supplies the job's short-lived token automatically; the workflow grants `contents: read`, `pages: write`, `id-token: write`, and `issues: write`.

[.github/workflows/daily.yml](.github/workflows/daily.yml) runs only on pushes to `main` changing `data/reports/**` or `site/**`, or manual `workflow_dispatch` on `main`. It checks committed artifacts, uploads the committed `site/` directory, deploys Pages, and then calls the notifier. It never fetches arXiv, runs a model, renders a report, commits, or pushes. The Pages steps use the [official Pages upload action](https://github.com/actions/upload-pages-artifact) and [deployment action](https://github.com/actions/deploy-pages).

The notifier finds the latest dated JSON in committed `data/reports/` and its corresponding committed PDF. It does not use `run_metadata.json`. It creates or reopens the persistent **Daily math.DS Digest notifications** Issue and adds one comment per report date, updating that comment when content changes. Pagination prevents duplicate notifications as the archive grows. An empty archive deploys the starter page and skips notification; an incomplete latest report fails the check.

GitHub Issue notifications are enabled by default. Subscribe to the persistent Issue and choose your GitHub notification preferences to receive GitHub-managed email or mobile alerts. Direct email is off by default and its credential-based sender has been removed. The existing email template is retained as an unused design reference.

If Pages or Issue posting is denied, check Pages configuration, repository Issues, and organization Actions permissions. A failed notification can be retried with manual dispatch without regenerating a report. Actual deployment and notification require a future authorized push and are not exercised by the offline test suite.
