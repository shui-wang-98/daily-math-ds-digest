# Offline inbox migration: acceptance evidence

Repair branch: `fix/offline-arxiv-input`. Production merge/deployment and
changes to the paused local task require separate user approval. All fixture
inputs, demonstrations and diagnostics remain under ignored `tmp/`.

## Baseline and diagnosis

- Initial clean main: `89c633d3d650e162ee22a5d91d94e6b447f58c43`.
- The remote repair branch already existed at that commit and was reused;
  no reset, force push or uncommitted changes were overwritten.
- Baseline: `.venv/Scripts/python.exe -m pytest -q`:
  **62 passed in 11.54s**, exit 0.
- The first sandboxed remote query failed before connection because Git's
  HTTPS helper was unavailable. A narrowly approved retry succeeded.
  This is not evidence of an arXiv network root cause.
- Previously reported WinError 10013 is not diagnosed from commands that
  failed to parse. The new local path avoids HTTP; global permissions and
  the paused task are unchanged.
- First implementation run: **14 failed, 48 passed**. A file-loop variable
  shadowed the provenance variable in finalization; its traceback identified
  the failure and the loop variable was renamed.
- Second run: **2 failed, 85 passed**. Explicit UTF-8 fixed new HTML test reads
  that had incorrectly used Windows' default GBK decoder.
- Third run: **87 passed in 9.36s**, exit 0. Command:
  `.venv/Scripts/python.exe -m pytest -q --tb=short`.
  Actual logs are under ignored `tmp/offline-input-validation/`.

## Design and reproducible checks

Cloud capture validates before saving an immutable announcement-date/SHA-256
XML/manifest pair. Local preparation reuses the original RSS parser and ID
filtering, resumes unfinished analysis, then processes backlog oldest first.
Analysis schema and mathematical reliability rules are unchanged. Finalization
retains provenance and atomically advances processed-input and seen-ID state
only after report/site promotion.

Report date follows feed pubDate in America/New_York. Capture time, feed build
time and local preparation/generation time are distinct. Inputs must be fresh
when captured; old valid backlog remains usable. Missing/stale/corrupt input
is an error, while a valid empty input is reportable. Same-day empty reruns
cannot erase nonempty reports. Tests block requests and sockets on the local
path and protect production data/inbox/state/reports/site.

Cloud capture targets weekdays 11:15 Europe/Warsaw. Prepared local instructions
target weekdays 12:00; the actual paused task is unchanged. Daily Git commands
use the existing narrow rules and fixed message `Add daily math.DS digest`.

Official references checked:

- [GitHub schedule timezone, delays and default-branch constraints](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
- [Official timezone support announcement](https://github.blog/changelog/2026-03-19-github-actions-late-march-2026-updates/).
- [Manual dispatch requires the workflow on the default branch](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).
- Official [checkout](https://github.com/actions/checkout),
  [setup-python](https://github.com/actions/setup-python) and
  [upload-artifact](https://github.com/actions/upload-artifact) documentation
  confirms the version 7 actions used here.

The repair-branch push workflow has only contents:read. It runs tests, downloads
official RSS into tmp, prepares it with HTTP blocked, and uploads an inspection
artifact. It does not publish, notify, commit or change production state.
The main-only capture job stages only its validated pair. The existing publisher's
path filters exclude inbox-only changes; tests enforce that separation.

## Executed local, visual and cloud validation

- Final local command: `.venv/Scripts/python.exe -m pytest -q`:
  **89 passed in 11.20s**, exit 0. Two additional regressions check reverse-order
  inbox insertion and prevent a fixture finalizer accidentally targeting the
  default production site when only data-dir was isolated.
- `git diff --check`: exit 0. Existing CRLF checkout warnings are informational.
- `codex execpolicy check --rules .codex/rules/math-ds.rules -- ...` returned
  allow for all four documented daily Git commands. The fixed commit message
  matches; no permission file or global setting was changed.
- Executed `.venv/Scripts/python.exe tmp/offline-input-validation/demo.py`
  with HTTP and socket calls blocked. All files are under
  `tmp/offline-input-demo-livecheck/`: normal report 2026-09-04, one paper in
  each priority; valid empty report 2026-09-07, all counts zero. Repeated
  finalization preserved file bytes. New dated outputs contain HTML/JSON only.
  The demo derives from the existing fixture and adds clearly labeled synthetic
  notation to its temporary abstract solely for formula rendering inspection.
- Actual in-app browser inspection at desktop width 1280 and mobile width 390:
  homepage newest-first dates, both date links, normal/empty counts, full HIGH
  and RELATED fields, both original abstract expanders, compact LOW entry,
  vector fraction and indexed notation, and wrapping were checked. No horizontal
  overflow was detected; browser warning/error log was empty. Viewport override
  was reset after inspection. External arXiv links were not requested.
- First real non-publishing CI:
  [run 34966256476](https://github.com/shui-wang-98/daily-math-ds-digest/actions/runs/34966256476),
  commit `c12dd265bd5fc525c42814e3afc2f1863b7fa6bf`, **success**.
  Downloaded actual runner logs confirm **87 passed in 12.25s**, successful
  official RSS capture, HTTP-blocked preparation, unchanged production data,
  and inspection-artifact upload. No deployment or notification step ran.
- Artifact `validated-live-rss`, ID `10394859604`, was downloaded and checked.
  Raw XML is 122704 bytes; SHA-256:
  `c2ead384a44e73215e6b26a60449e1dc3fbca5cfc22a4cfeea11a9ac47ae2441`.
  Fetch time: 2026-09-15 11:59:50.826540 UTC; announcement:
  2026-09-15 00:00:00 -04:00; feed build: 2026-09-15 04:00:23 UTC.
  It contains 30 new, 20 cross, 15 replace-cross and 9 replacement-only entries.
  The retained, unique pending set is **65** papers dated **2026-09-15**.
- Executed `.venv/Scripts/python.exe tmp/offline-input-validation/inspect_artifact.py`
  on Windows against that downloaded real artifact. Local preparation again
  produced 65 papers with requests and socket connections blocked, using isolated
  empty state under `tmp/offline-input-validation/real-local-prepared/`.
  It did not analyze or publish real papers or use production seen state.

## Changed files

- Source: `src/capture_feed.py`, `src/inbox.py`, `src/fetch_arxiv.py`,
  `src/prepare_run.py`, `src/finalize_run.py`, `src/models.py`.
- Tests: `tests/test_inbox.py`, `tests/test_workflows.py`, `tests/conftest.py`.
- Workflows: `.github/workflows/capture-rss.yml`, `.github/workflows/validate-offline.yml`.
- Instructions/evidence: `AGENTS.md`, `DAILY_AUTOMATION.md`, `README.md`,
  `SETUP_CHECKLIST.zh-CN.md`, `VALIDATION.md`.

Research profile, analysis schema, requirements, templates/styles, existing
publisher workflow, project permissions, production reports/state/site and
legacy downloads are unchanged. The actual paused task and user-level Codex
configuration are unchanged. Diagnostic scripts/logs are ignored, not committed.

## Outstanding production acceptance

After approved merge/deployment, verify real input committed to main, local Git
sync, actual Codex English analysis, HTML/JSON, automatic daily commit/push,
Pages deployment and the persistent Issue update. Inspect a real Scheduled Task
run/log. Interactive success and CI success do not establish unattended operation.
If the product cannot trigger or inspect that task, request only the necessary
real run or log. Do not publish fixture reports or test notifications.

## Historical context

The 2026-09-08 HTML-only migration recorded 62 passing tests and isolated browser
checks. The 2026-09-07 migration recorded 44 passing tests for the retired
multi-format pipeline. Those are historical results, not evidence that this new
architecture or an unattended production run has passed.
