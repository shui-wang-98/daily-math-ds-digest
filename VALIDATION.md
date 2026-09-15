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

## Outstanding acceptance

Final local test/diff results, demonstrations, visual inspection and real CI
results will be added here only after execution.

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
