# Offline inbox migration: acceptance evidence

Current status (2026-09-15): production deployment was approved and completed;
the real cloud capture, local offline analysis, fixed-message Git publication,
Pages and Issue notification passed. The existing local task is ACTIVE with
updated inbox instructions. Its actual already-finalized retry passed; its
unattended analysis and publication of new input remain unverified.
Detailed production and task evidence is below. Earlier sections record
the pre-approval repair branch `fix/offline-arxiv-input` and its historical
checks, not the current task/deployment status. All fixtures and diagnostics
remain under ignored `tmp/`.

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
  the paused task were unchanged during that pre-approval repair phase.
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
target weekdays 12:00; the task was kept paused during the repair phase. Daily Git commands
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
legacy downloads were unchanged during pre-approval validation. The task and
user-level Codex configuration were unchanged then. Diagnostic scripts/logs are
ignored, not committed. All 15 initially snapshotted protected files retained
identical SHA-256 hashes at that stage.

## Outstanding unattended acceptance

Production publication and the actual task's already-finalized retry are verified
below. That retry correctly skipped analysis, finalization, tests, commit and
push, so it does not establish unattended publication of new input. Inspect the
next real task run with new input to close that remaining gap. Interactive
success and CI success cannot substitute for it. The enabled automation tool
exposes no run-now operation; native app control is unavailable. Do not use a
follow-up chat message, changed schedule or artificially reset state as pretend
scheduler evidence. Another empty retry is unnecessary. No fixture report or
test Issue notification is authorized.

## Historical context

The 2026-09-08 HTML-only migration recorded 62 passing tests and isolated browser
checks. The 2026-09-07 migration recorded 44 passing tests for the retired
multi-format pipeline. Those are historical results, not evidence that this new
architecture or an unattended production run has passed.
## Production acceptance: 2026-09-15

The first production finalization also exposed valid source-TeX spellings not
accepted by the vector renderer: unbraced bold Greek arguments and compact
fractions. An original abstract also used an equation environment, and another
used a text block containing inline mathematics. The renderer now handles
these forms without modifying archived source text; regression tests check
formula grouping and intervening prose. The failed finalization left every
preexisting report/site/state byte unchanged. This was an actual rendering
failure, not evidence about network access.
Inspection also reproduced silent removal of an undefined macro naming a
property in prose. Such macros now retain their literal names and an explicit
source-notation note rather than deleting the property from the sentence.

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
with state bytes unchanged.

### Completed production results

- Deployment fixes: `bf690bb` adds `.gitattributes` and `tests/test_git_transport.py`;
  `fd454c7` updates `src/math_render.py` and its tests; `41c6aac` preserves
  standard author accents/separators and undelimited tau notation. No research
  profile, dependency, permission file, publisher workflow or template/style changed.
- Final complete local command: `.venv/Scripts/python.exe -m pytest -q`,
  **98 passed in 12.73s**, exit 0. `git diff --check` passed. Earlier final-code
  runs passed 98 tests in 16.03s and 16.78s. The post-finalization suite protects
  production file bytes and timestamps. `src.notify --check-only` passed.
- Final code CI on `41c6aac`:
  [34977828842](https://github.com/shui-wang-98/daily-math-ds-digest/actions/runs/34977828842),
  **success**, downloaded logs confirm **98 passed in 6.79s**, live official
  capture and HTTP-blocked preparation. Inspection artifact: `10400306277`.
- Codex read all 65 supplied titles/abstracts and authored English analysis:
  **12 HIGH PRIORITY, 27 RELATED, 26 LOW PRIORITY**. Report/announcement date:
  **2026-09-15**. All 30 new, 20 cross and 15 replace-cross entries appear once;
  all 9 replacement-only entries are excluded. No API/AI service or full-paper
  access was used. Static arXiv URL/ID checks made no arXiv requests.
- Actual default production finalization succeeded. Output paths:
  `data/reports/2026-09-15.json`, `site/reports/2026-09-15/index.html`,
  `site/reports/2026-09-15/report.json`, `site/index.html`, `data/state.json`.
  The state records the 65 seen IDs and immutable input only after output
  promotion. Prior failed attempts changed no state/archive bytes.
- Full metadata/abstract equality, schema/coverage/counts, static links,
  provenance, original abstract HTML, LOW empty-field policy, and every prior
  report/legacy download hash were checked by an ignored inspection script.
  Re-finalization with HTTP/socket blocked preserved every data/site byte.
  A subsequent `src.prepare_run` returned **exit 3**, already finalized, with
  no file changes. No new PDF/Markdown was generated and none was rewritten.
- Actual browser inspection covered the homepage and dated report at desktop
  and 390-pixel width. All 39 original abstracts were expanded; formula images
  loaded successfully and no horizontal overflow occurred. All 26 LOW list
  items had exactly title link, authors, and identifier, with no digest/abstract.
  Date links list 2026-09-15 then 2026-09-07; only the historical date links
  legacy downloads. Standard author accents and source-notation handling were
  corrected during this inspection. Undefined source macros remain literal
  with explicit notes, without guessing definitions.
- Daily publication commit **`dd98b65a7dfe4c87876944ecb8dfbcea37eef737`** used
  exactly **`Add daily math.DS digest`**, staging only the five files above.
  `git push origin main` succeeded. Inbox was not staged locally.
- Production publisher
  [34977929875](https://github.com/shui-wang-98/daily-math-ds-digest/actions/runs/34977929875)
  **succeeded**, including Pages and Issue notification. Actual logs were read.
  The [homepage](https://shui-wang-98.github.io/daily-math-ds-digest/),
  [HTML report](https://shui-wang-98.github.io/daily-math-ds-digest/reports/2026-09-15/)
  and [published JSON](https://shui-wang-98.github.io/daily-math-ds-digest/reports/2026-09-15/report.json)
  returned HTTP 200 and matched local bytes exactly. Exactly one date-marked
  [Issue comment](https://github.com/shui-wang-98/daily-math-ds-digest/issues/1#issuecomment-5681352998)
  contains 12/27/26 and the correct public links. Inbox-only capture did not
  create a publisher run or completion notification.
- Existing automation `daily-local-math-ds-report`, name `Daily local math.DS report`,
  was updated via the product tool and verified ACTIVE. Its existing heartbeat
  kind, target task, name and weekday 12:00 Europe/Warsaw cadence were preserved.
  It now follows the current offline/retry/publication procedure. No new task,
  global configuration, credential or broad permission was created.
- The local production generation/publication above ran in the interactive
  session. The subsequent real task retry is recorded below; unattended Git
  writes with new input and schedule punctuality remain unverified.

## Actual task retry and PowerShell exit-code diagnosis: 2026-09-15

The user supplied the completed task result. The task API and its actual local
session log were inspected, including command arguments, outputs and exit codes:

- Task: `Daily local math.DS report`, ID
  `01a0a4a6-b788-7770-afa6-a658962a4a6b`.
- Turn: `01a0a55f-1f13-7e71-b368-a60578423cad`, started
  `2026-09-15T14:01:09Z`, completed `2026-09-15T14:02:39Z`
  (16:01-16:02 Europe/Warsaw). The log includes the actual automation heartbeat
  invocation, not a substitute follow-up chat prompt.
- `git pull --ff-only origin main`: exit 0, `Already up to date.`
  The task checked `main`, a clean working tree and no commits ahead of origin.
- `.\.venv\Scripts\python.exe -m src.prepare_run`: printed
  `All available current inputs are already finalized; no files changed`.
  Its `pwsh.exe -Command` wrapper reported exit 1. The task inspected the
  handler returning 3 and stopped without rewriting or republishing reports.
- Existing report date 2026-09-15, counts 12/27/26, all four output paths and
  digest commit `dd98b65a7dfe4c87876944ecb8dfbcea37eef737` were confirmed.
  Analysis, finalization, tests, commit, push and notification checks were
  correctly skipped. The task also saved its run memory successfully.

The exit discrepancy was then reproduced with actual terminal-tool calls in
the same checkout. A plain `.\.venv\Scripts\python.exe -m src.prepare_run`
returned tool exit **1**. Adding an immediate `exit $LASTEXITCODE` in the same
PowerShell call returned tool exit **3**, with identical already-finalized output
and no repository changes. This is documented
[PowerShell -Command behavior](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_pwsh?view=powershell-7.5#-command---c):
the shell normalizes native nonzero codes unless explicitly propagated.
It is not an application or arXiv network failure.

`DAILY_AUTOMATION.md` now requires that exact two-line invocation and handling
of the preserved status. README and the deployment checklist point to the same
procedure. The existing task reads those instructions at every invocation;
no task configuration, permission rule or application-code change is needed.
This follow-up changes only those three documents and this evidence file, with
`git diff --check` used for validation. The full suite was not rerun for this
documentation-only correction; the most recent runtime result remains 98 passed.
No source, tests, workflow, inbox, analysis, state, report or site file changed.

Verified scope: actual task Git pull, offline inbox preparation and safe
already-finalized stopping. Still unverified: the corrected exit propagation
inside a subsequent task invocation, unattended new-input analysis and Git
add/commit/push, and weekday 12:00 scheduling punctuality. A real future input
is required for the remaining publication acceptance; do not reset state,
reprocess September 15 or publish a synthetic report to manufacture that test.

## Subjects and followed authors: 2026-09-15

The user requested replacing Prerequisites with Subjects and following new
papers by named authors, initially Ruxi Shi and Masaki Tsukamoto. Implementation
is on `codex/subjects-author-watchlist`; this section does not claim that the
new feature has been deployed or exercised by the scheduled task.

- Baseline command `.venv/Scripts/python.exe -m pytest -q`: **98 passed in 13.86s**.
- The unchanged earlier suite also passed after the initial implementation:
  **98 passed in 17.62s**.
- Targeted author/Git transport checks: **19 passed in 4.13s**.
- Full updated suite: `.venv/Scripts/python.exe -m pytest -q`,
  **116 passed in 21.36s**, exit 0. `git diff --check` passed.
- New `author_watchlist.yaml` stores the two names, all-subject scope and the
  UTC first-submission start date 2026-09-15. Official arXiv Atom author queries
  run only in cloud capture, with pagination, exact normalized-name matching,
  three-second serial page spacing, validated dates/metadata/links and immutable
  original bytes. No model API, key, local network grant or task change is used.
- Raw author pages and their watchlist/URL/hash metadata join the existing
  RSS bundle. RSS-only historical IDs stay stable. Both inputs reuse the same
  offline preparation, seen-ID deduplication, analysis schema and finalization.
  Missing author input fails explicitly; a complete later bundle lets older
  RSS-only backlog finish without silently dropping it.
- Matched authors require full HIGH PRIORITY analysis, appear first with an
  IMPORTANT marker and are listed in the existing Issue notification. This is
  an explicit user preference, not a change to the mathematical research profile.
- Subjects comes from original category metadata. Prerequisites is absent from
  new schema/output and HTML. Historical JSON and unfinished legacy analysis
  remain readable. Existing JSON, state and PDF/Markdown are not migrated.
- Regression tests derive synthetic Atom records from the existing RSS fixture.
  They cover invalid/empty/missing/stale/partial data, immutable hashes, complete
  pagination, full-name versus initial/substring matching, offline HTTP/socket
  blocking, duplicate IDs, same-day preservation, priority enforcement, retry,
  original submission dates, HTML/JSON, notification content, archive compatibility,
  and Git autocrlf preservation of author XML. Tests protect production bytes
  and timestamps. No synthetic input or report belongs in production.

Cloud CI and browser evidence will be recorded after actual execution.
