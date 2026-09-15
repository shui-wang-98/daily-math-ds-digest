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
- Final review reproduced another boundary failure: an item without pubDate
  was accepted, allowing the legacy parser's current-time fallback to make its
  metadata unstable across retries. The targeted regression initially failed
  (DID NOT RAISE). Capture now requires each item's announcement date to match
  the feed date; the compatibility parser itself remains unchanged.

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
  **90 passed in 10.96s**, exit 0. Additional regressions check reverse-order
  inbox insertion and prevent a fixture finalizer accidentally targeting the
  default production site when only data-dir was isolated, and reject missing
  item announcement dates before persistence. The earlier isolation run passed
  89 tests in 11.20s.
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
  The temporary HTTP server logged only a non-blocking missing favicon request
  (404); HTML and stylesheet requests succeeded. The test tab and server were
  closed after inspection.
- First real non-publishing CI:
  [run 34966256476](https://github.com/shui-wang-98/daily-math-ds-digest/actions/runs/34966256476),
  commit `c12dd265bd5fc525c42814e3afc2f1863b7fa6bf`, **success**.
  Downloaded actual runner logs confirm **87 passed in 12.25s**, successful
  official RSS capture, HTTP-blocked preparation, unchanged production data,
  and inspection-artifact upload. No deployment or notification step ran.
- Second real CI:
  [run 34967193024](https://github.com/shui-wang-98/daily-math-ds-digest/actions/runs/34967193024),
  commit `47f83af5d8b695515897dcd77a78c7e0ef423d44`, **success**;
  downloaded logs confirm **89 passed in 5.93s** and successful real capture
  plus HTTP-blocked preparation. The item-date hardening is tested in the
  subsequent final-code run recorded below.
- Final runtime-code CI:
  [run 34967661474](https://github.com/shui-wang-98/daily-math-ds-digest/actions/runs/34967661474),
  commit `7d4074baa733a615d59e4335b8950b7715a0b533`, **success**.
  Downloaded logs confirm **90 passed in 6.02s**, real official RSS capture
  at 2026-09-15 12:14:20.822666 UTC, the same 122704-byte XML/SHA-256 recorded
  below, and successful HTTP-blocked preparation of 65 IDs. Inspection artifact
  ID: `10395707966`. All steps succeeded, with no publication permissions or
  actions. The follow-up commit recording this evidence changes documentation
  only; it does not change the validated runtime code or workflows.
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
All 15 initially snapshotted protected files retain identical SHA-256 hashes.

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
# Production acceptance: 2026-09-15

After explicit deployment approval, main was fast-forwarded to `3dd2f3d`.
The first production capture succeeded in
[run 34975423235](https://github.com/shui-wang-98/daily-math-ds-digest/actions/runs/34975423235),
committing only the immutable RSS/manifest pair as `c46db2f`. It did not start
the publisher. Capture time: `2026-09-15T13:30:34.547632Z`; announcement date:
`2026-09-15`; raw size: 122704 bytes; SHA-256:
`c2ead384a44e73215e6b26a60449e1dc3fbca5cfc22a4cfeea11a9ac47ae2441`.

The real Git-to-Windows hop exposed a failure absent from artifact testing:
`core.autocrlf=true` changed RSS line endings and correctly caused input hash
validation to fail. State and reports were untouched. `.gitattributes` now sets
`data/inbox/**/feed.xml -text`, preserving original bytes in every checkout.
`test_raw_rss_survives_autocrlf_checkout` exercises an actual temporary Git index
and checkout with autocrlf enabled. Rechecking out the affected cloud input
restored its exact manifest hash; no input content was regenerated or changed.

The source-less pending/analysis pair left from 2026-09-07 was verified against
all 18 archived paper records, analysis fields, and seen-state entries. Exact
copies remain in ignored `tmp/offline-input-validation/completed-legacy-2026-09-07/`.
The completed pending file was retired only after those checks. Production
preparation then found 65 unseen papers while HTTP and socket calls were blocked,
with state bytes unchanged. Further publication acceptance is recorded below
when executed; these observations alone do not verify an unattended task run.
