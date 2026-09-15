# Daily math.DS Digest

An English research digest from official arXiv math.DS titles and abstracts.
GitHub Actions captures raw RSS; local Codex synchronizes it through Git and
writes the analysis. Python validates and renders locally. No model API, AI SDK,
paid AI service, new key, or direct email credential is used.

## Architecture and schedules

Cloud capture (weekdays 11:15 Europe/Warsaw) -> committed inbox -> local Git sync
-> offline preparation -> Codex analysis -> HTML/JSON -> validated Git commit/push
-> existing Pages workflow and persistent Issue notification.

The existing local task targets weekdays **12:00 Europe/Warsaw** and was updated
and resumed after production approval on 2026-09-15. The real cloud-input through
Pages/Issue path has passed. The actual task's already-finalized retry also
passed; its unattended analysis and publication of new input remain unverified.
See [VALIDATION.md](VALIDATION.md) for evidence and follow
[DAILY_AUTOMATION.md](DAILY_AUTOMATION.md). Editing repository instructions does
not itself change or trigger the task. Local execution requires the computer awake and the desktop app
running; see the [official task documentation](https://learn.chatgpt.com/docs/automations?surface=app).

## Cloud capture

[capture-rss.yml](.github/workflows/capture-rss.yml) downloads only
`https://rss.arxiv.org/rss/math.DS`. It validates RSS structure, math.DS category,
timestamps, announcement types, metadata, URL/ID correspondence and freshness
before saving anything. Raw XML response bytes are preserved without reserialization;
`.gitattributes` disables Git line-ending conversion for inbox XML, including Windows checkouts:

```text
data/inbox/ANNOUNCEMENT-DATE/SHA256/feed.xml
data/inbox/ANNOUNCEMENT-DATE/SHA256/manifest.json
```

The manifest includes source URL, fetch time, feed publication/build timestamps,
announcement date, byte count, SHA-256, and the capture CI URL when available.
Only a complete pair is promoted. Existing captures, including processed inputs,
are never overwritten; identical bytes create no additional commit.

Freshness means the announcement date equals the capture day's latest weekday
in Europe/Warsaw (Friday on weekends). Future/inconsistent feed timestamps fail.
Delayed announcements and exceptional holidays are **input not ready**, not
empty days. The pipeline does not guess a holiday calendar. Previously validated
inputs remain eligible for backlog processing even when the computer was offline.

The workflow provides manual dispatch and weekdays 11:15 Europe/Warsaw.
GitHub officially supports an IANA `timezone` beside `cron`, follows daylight
saving, can delay scheduled jobs, and uses the default branch:
[official schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
The capture job uses only built-in GITHUB_TOKEN with `contents: write`, stages
only its XML/manifest pair, and does not analyze, change state, deploy or notify.
Concurrent main updates can reject its ordinary push; retry the failed job,
never force-push or add a new secret.

## Local preparation and analysis

Use Python 3.12+ and the repository's virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Use executables directly if activation/PATH is unavailable. No global permission
change is needed; tzdata supplies Windows timezone data.

After synchronizing the intended clean main checkout with
`git pull --ff-only origin main`, run `python -m src.prepare_run`.
The formal path reads only the oldest unfinished validated local inbox input,
using the existing parser, normalized IDs and seen state. It includes new,
cross and replace-cross announcements and excludes replacement-only submissions.
There is no HTTP request or network fallback.

- Exit 0: pending metadata is ready, including a valid input with no unseen papers.
- Exit 2: **INPUT NOT READY**; inspect the missing/stale/corrupt input, never write an empty report.
- Exit 3: current captured inputs were already finalized; no files changed.

For a PowerShell command-runner invocation, immediately follow preparation with
`exit $LASTEXITCODE` in the same call, as shown in
[DAILY_AUTOMATION.md](DAILY_AUTOMATION.md#scope-and-start), to preserve these codes.

Unfinished pending/analysis survives a preparation retry. Finish it before
processing the next oldest capture. Report date follows channel pubDate in
America/New_York; cloud fetch time, feed timestamps and local preparation/generation
times remain separate. Old backlog must never be relabeled as today's news.

`--inbox-dir PATH` selects an isolated inbox. Existing `--local-feed PATH`
remains available for fixtures, requires a non-production `--data-dir`, and
is the only mode accepting `--report-date`. Its compatibility default remains
the local run date. Never use fixtures for production recovery.

Codex reads every supplied title and abstract and writes the unchanged
[analysis schema](schemas/analysis_run.schema.json). Follow the full research
profile in [config.yaml](config.yaml), [AGENTS.md](AGENTS.md), and
[DAILY_AUTOMATION.md](DAILY_AUTOMATION.md). Missing information must be
“Not specified in the abstract.” Do not invent mathematical claims or proof methods.

## Finalization, reports and recovery

```powershell
python -m src.finalize_run --analysis data/analysis_run.json
pytest -q
python -m src.notify --check-only
```

Finalization verifies the immutable input and its pending metadata, retains
contributing manifests in report `source_inputs`, and produces only:

```text
data/reports/YYYY-MM-DD.json
site/reports/YYYY-MM-DD/index.html
site/reports/YYYY-MM-DD/report.json
site/index.html
site/assets/style.css
site/.nojekyll
data/state.json
```

Only after all outputs are promoted does one atomic state write record both
seen IDs and `processed_inputs`. Rendering failures leave the archive intact.
A disk error during individual file promotion can leave partial artifacts,
but never advances state. Keep pending/analysis and rerun the finalizer.
Identical reruns preserve bytes/timestamps; same-day additions merge, and empty
reruns cannot erase a nonempty report. Completed analysis remains in archive JSON.

The existing English design, responsive layout, native original-abstract
expanders, research profile, three priorities and mathematical reliability rules
are preserved. HIGH/RELATED have all digest fields and original abstracts;
LOW shows only title, authors and arXiv ID. Formulas are embedded SVG, with no
remote scripts/fonts/CDN. Validate external URLs against IDs locally, without HTTP.

The permanent homepage lists all dates newest first, with counts and links.
New human-readable output is HTML only. Existing PDF/Markdown files are preserved
and linked only when present. Browser Ctrl+P -> Save as PDF remains optional.
`python -m src.rebuild_site` rebuilds HTML/assets from archived metadata without
changing state, JSON, or historical PDF/Markdown.

## Testing and isolated demonstrations

Fixtures are synthetic. Use fresh ignored data/site/inbox paths under `tmp/`,
never production. For the compatible fixture route:

```powershell
python -m src.prepare_run --local-feed tests/fixtures/math_ds.xml --report-date 2026-09-04 --data-dir tmp/offline-input-demo/data
Copy-Item tests/fixtures/analysis_run.json tmp/offline-input-demo/data/analysis_run.json
python -m src.finalize_run --analysis tmp/offline-input-demo/data/analysis_run.json --data-dir tmp/offline-input-demo/data --site-dir tmp/offline-input-demo/site
```

Tests block HTTP, exercise inbox and fixture routes, simulate failures and
assert production data/inbox/state/reports/site remain untouched.
[VALIDATION.md](VALIDATION.md) records actual test, visual and CI evidence.

[validate-offline.yml](.github/workflows/validate-offline.yml) runs on repair
branch pushes and pull requests with only `contents: read`. It tests, captures
real official RSS under `tmp/ci-inbox`, prepares it with HTTP blocked, and uploads
inspection artifacts. It never publishes, notifies, commits, or updates production
state. Branch push is intentional: a new workflow cannot rely on dispatch before
it exists on the default branch.

## Publication and permissions

The authorized daily task uses the existing exact command prefixes:

```text
git pull --ff-only origin main
git add -- data/state.json data/reports site
git commit -m "Add daily math.DS digest"
git push origin main
```

Inspect the full generated diff before staging, then inspect the staged diff.
Never stage inbox inputs locally, unrelated changes, pending/analysis, fixtures,
temporary outputs or modifications to legacy downloads. Do not use a dated
commit message, broad permission rule, global setting change or force push.

The unchanged [daily.yml](.github/workflows/daily.yml) triggers only for main
report/site changes or manual main dispatch. Its path filters exclude inbox-only
pushes; capture never dispatches the publisher. It checks committed artifacts,
deploys the site and creates/updates one persistent Issue comment per report date.
Pages must use GitHub Actions; Issues must be enabled. The publisher's built-in
token has contents:read, pages:write, id-token:write and issues:write.
Subscribe to the Issue for GitHub-managed alerts; do not send a local duplicate.

Maintenance is validated on a repair branch. Merge/deployment requires user
confirmation. Interactive or CI success does not prove unattended Scheduled Task
execution; that real production acceptance remains separate.
