# Hosted cloud daily digest

The user authorized replacing the local daily schedule with hosted cloud
execution on 2026-10-09 and repairing capture/recovery on 2026-10-14. The primary
run targets Monday-Friday at 12:00 Europe/Warsaw; a hosted recovery check targets
20:00 on the same days. Both execute this identical idempotent procedure, in
fresh disposable workspaces. Do not depend on earlier chat history; the current
repository instructions and main state are authoritative. Keep the old local task paused.
A saved schedule is not evidence that capture or publication has succeeded.

The existing GitHub capture workflow starts at 11:00 Europe/Warsaw on weekdays,
with recovery checks at 11:15, 11:30 and 11:40. It is a prefetch opportunity,
not a prerequisite for hosted analysis. The hosted run also archives missing
current-day input before analysis using the same strict capture implementation.
An existing valid input is reused without HTTP. Neither scheduler guarantees
delivery during a platform outage; the 20:00 check provides another opportunity
and must report remaining missing input or failed publication honestly.

## Authority and environment

Use only hosted cloud tools, a disposable cloud checkout of
`https://github.com/shui-wang-98/daily-math-ds-digest`, and the existing connected
GitHub plugin. Never use a connected local computer, a Windows path, or a local
executor, even as a fallback. If hosted execution or repository access is
unavailable, report BLOCKED with the real reason.

This procedure replaces the local-only environment, dependency-installation,
input acquisition and Git transport steps in DAILY_AUTOMATION.md. The sole
network acquisition exception is the hosted capture phase below; preparation
and analysis remain offline. Read that file completely and
retain all its research, coverage, mathematical, rendering, state, and
publication-scope rules. Also read AGENTS.md, config.yaml, author_watchlist.yaml,
src/models.py, schemas/analysis_run.schema.json, both prompts, requirements.txt,
and pytest.ini at the checked-out revision before analysis.

Record the actual UTC start time, operating system, Python and Node versions,
and main commit SHA. Read the remote main head with the GitHub plugin and obtain
a complete checkout at that exact revision; verify its HEAD and clean tracked
files. Do not assume the previous run's filesystem persists. GitHub main is the
durable record of finalized inputs and outputs.

Create a virtual environment under an isolated absolute cloud temporary path.
Install only dependencies declared in requirements.txt and their dependencies.
Use the cloud's existing Node.js 18 or newer; verify it is discoverable by the
same process environment used for finalization and tests. Preserve the Node
directory when setting PATH: the initial cloud acceptance test failed when an
isolated PATH omitted it. Do not install model SDKs, use a model API or AI API
credential, read secrets, change access permissions, or modify global settings.

Do not modify application code, tests, workflows, configuration, research
preferences, these instructions, or schedules during a daily run. Temporary
analysis/check scripts are allowed only in the disposable cloud workspace.

## Secure the current input before processing backlog

Do this at the start of every invocation, before potentially lengthy analysis.
Only the official `https://rss.arxiv.org/rss/math.DS` feed may be fetched, by
`src.capture_feed` in this hosted workspace. Never fetch paper links, other
categories, author APIs, fixtures, or a local-computer fallback. Do not loosen
validation or invent inputs for missing historical days after RSS has rolled on.

1. Validate **all** existing captures first, including older processed inputs:
   `python -c "from pathlib import Path; from src.inbox import read_inbox; print(len(read_inbox(Path('data/inbox'))))"`.
   A corrupt or incomplete pair is a hard failure. Do not fetch another input
   to conceal it. Record the paths and exact error and stop.
2. Run `python -m src.capture_feed --if-missing --json`. Its JSON describes
   the validated source, input ID, path base, exact two files and filtered paper
   count. In the production checkout `path_base` must be `repository` and the
   two files must be exactly `data/inbox/<input_id>/feed.xml` and
   `data/inbox/<input_id>/manifest.json`. Zero papers is valid only after the
   RSS, timestamps, date, content and hash checks succeed.
3. If the pair was already present in the base tree, require unchanged bytes
   and make no capture commit. Otherwise, inspect both files with `read_input`,
   compare their source identity against the CLI output, and atomically publish
   **only these two new files**. Use the Git-data blob/tree/commit/ref procedure
   below with message `Capture math.DS RSS input`, the current base tree/parent,
   `expected_sha=base_SHA` and `force=false`. Reject deletions, overwrites and
   any other changed path. This capture commit must not contain state, reports,
   pending or analysis. Verify remote hashes and bytes before continuing.
4. On a capture lease rejection, refresh main and validate its inbox. If the
   exact same input hash is already archived, reuse the remote pair unchanged
   (especially its original fetched_at); do not overwrite it with local capture
   metadata. For another concurrent update, obtain a fresh checkout and repeat
   the check at most twice. Unknown outcomes require readback before retrying.
   Stop on unresolved conflicts. Never bypass the lease or force a ref update.
5. After a successful capture write, use a new clean checkout at the verified
   remote main SHA for preparation. The earlier checkout's HEAD is stale.
   For reuse without a write, recheck remote main and refresh if it advanced.
6. A download error, stale feed or missing current-day feed is **INPUT NOT READY**,
   not a zero-paper report. Preserve its actual error. Existing validated older
   captures may still be processed by offline preparation in date order; do not
   let a transient current-day download failure strand an already archived day.
   Never create a current-day report without its validated input. End the run
   with the capture stage failed/pending even if backlog publication succeeds.
   Do not loop indefinitely or create a new schedule; the saved recovery task
   checks again at its scheduled time.

## Generate and validate

Before the first preparation or analysis, **both primary and recovery runs**
must check publication of the latest committed report. Find the commit that
actually introduced that report (current main may be a later capture commit),
then verify its exact publisher run, public files and Issue marker as described
below. If pending, wait with the bounded backoff; if still pending or failed,
stop subsequent report generation and report the specific failed stage. This
gate must not depend on prepare returning exit 3. An empty repository with no
report has nothing to verify and may proceed.

1. Run the checkout's `python -m src.prepare_run` with the isolated interpreter,
   preserving the actual exit code. This is offline and reads immutable
   `data/inbox/` only; this command must never make HTTP requests or substitute
   fixtures. Exit 2 means INPUT NOT READY; report the cause without
   inventing an empty report. Exit 3 means NO NEW INPUT and requires no report
   rewrite or publication, but still check the latest committed report's
   deployment/notification if a previous invocation left publication pending.
   Exit 0 may legitimately contain zero papers.
2. Process unfinished captures oldest first, using each pending report date,
   not the execution date. Preserve pending and analysis throughout retries
   within the run. If a previous run left a recovery attachment, inspect its
   input hash, base revision, and existing finalized state before using it.
3. Personally read and classify every supplied title and abstract, then author
   English data/analysis_run.json under the validated schema and profile.
   Followed-author matches must be HIGH PRIORITY with full digests and their
   author relevance note. HIGH PRIORITY and RELATED require complete digests;
   LOW PRIORITY uses the prescribed empty digest fields. The earlier one-off
   backlog cap of ten main entries is not a permanent daily classification rule.
   Do not request or add Prerequisites. Use only title/abstract evidence and
   the exact missing-information phrase from DAILY_AUTOMATION.md. Preserve
   hypotheses, qualifications, notation, and valid paired LaTeX delimiters.
4. Run `python -m src.finalize_run --analysis data/analysis_run.json`. Generate
   HTML and JSON only and preserve all historical PDF/Markdown bytes. Inspect
   every generated file, full coverage, counts, original abstracts, mathematics,
   provenance, author markers, state, archive ordering, and links. Validate
   arXiv URL/ID correspondence without requesting paper URLs. Render desktop
   and narrow pages when browser/rendering tools are available; report any
   unavailable visual check accurately.
5. Run `python -m pytest -q --basetemp=ABSOLUTE_ISOLATED_TEMP_PATH` and
   `python -m src.notify --check-only`. All tests must pass; investigate skipped
   tests caused by missing runtimes instead of accepting a degraded environment.
   The migration baseline is 396 tests; use the full current suite, not a fixed
   expected count. Test fixtures and synthetic files must remain isolated from
   production data, site, and inbox.
6. Confirm artifacts exist before state advances. Rerun finalization with the
   identical pending/analysis pair and verify output/state hashes are unchanged.
   Inspect `git diff --check`, all changed/untracked paths, and the full diff.
   Stop on unresolved mathematics, schema, rendering, or test failures.

## Publish atomically with the connected GitHub plugin

User authorization covers the separately validated capture pair above,
committing validated daily outputs to main and the
existing GitHub publisher's deployment and persistent Issue notification.
It does not authorize unrelated code changes, new credentials, new Issues, or
additional notification channels.

Use the connected GitHub Git-data tools instead of relying on shell Git push
credentials. Never copy plugin credentials into the shell. Do not publish
files separately through create_file/update_file: readers must never observe
state advanced before its complete output set.

1. For a **report** commit allow only the validated run's data/state.json, dated JSON in data/reports/,
   dated index.html/report.json in site/reports/, site/index.html, and required
   site/assets/ or site/.nojekyll. Reject every other changed path and any
   deletion, legacy PDF/Markdown modification, executable-mode change, symlink,
   pending/analysis file, inbox, fixture, temporary file, dependency, or secret.
   Inspect exactly the complete list and bytes to be published.
2. Re-read main immediately before publishing. Its head must still equal the
   checkout base SHA. Obtain that commit's tree SHA. Upload exact validated file
   bytes as blobs (base64 is suitable); build one new tree with that existing
   tree as base, replacing only the allowlisted files. Preserve every other
   path. Inspect the resulting tree/change set against the base.
   Transfer file bytes programmatically through the available tool orchestration,
   not by asking the model to copy HTML: existing pages can exceed 900 KB. If
   necessary, read bounded base64 chunks into an orchestration variable and
   assemble the complete content there without printing it into model context.
   Verify each returned Git blob SHA against the locally computed Git blob SHA
   and verify readback bytes/hashes. Never upload truncated tool output or
   hand-reconstructed content. If the cloud tools cannot transport the complete
   file to the plugin, report BLOCKED and preserve the validated output.
3. Create one commit with that tree, the unchanged base SHA as parent, and the
   exact message `Add daily math.DS digest`. Advance main using update_ref with
   expected_sha equal to the base SHA and force=false. This is the atomic
   publication point. Never force-push, delete a ref, or create another branch.
4. Verify main now points to the new commit and read back the changed blobs to
   confirm they match the validated bytes. On a timeout/unknown outcome, inspect
   main before retrying; never blindly create another publication. On a lease
   rejection or concurrent update, stop and report the conflict. Do not silently
   overwrite newer state. Preserve the pending/analysis pair and validated
   outputs as a recovery attachment to the cloud run where supported, recording
   the base SHA and input hash; never commit recovery files to the repository.
5. If no generated diff exists, make no empty commit. If retrying an already
   published input, verify the remote output and publisher state instead of
   reanalyzing or republishing it. A fresh cloud workspace can regenerate an
   unpublished input because its processed state was never published.

## Verify deployment and report

The existing `.github/workflows/daily.yml` publisher handles Pages and the
persistent Issue. Do not call notify without --check-only and do not post an
extra Issue/comment/email. Read Actions runs for the exact published head SHA
(the connector's PR-only workflow helper is not sufficient for push runs).
Verify the Publish math.DS digest job, public dated HTML/JSON and homepage, and
the existing Issue's matching report-date marker/counts/links. Never request
arXiv links during these checks.

Recovery invocations first check any already committed latest report whose
publisher is unfinished, instead of making another report commit. A queued
publisher is pending; a failed publisher is a real failure requiring attention.
Do not duplicate Issue comments or re-upload identical outputs to force a run.

Wait reasonably with backoff for publication (up to 15 minutes per input).
If queued, blocked, failed, or not triggered, report that actual status and run
link. Do not change runners, billing, permissions, workflows, or schedules to
resolve it; do not label an unverified deployment successful. Preserve the
successful commit separately from deployment/notification status. Only after
one input is verified published should the sequence continue to the next
unfinished capture in order. Stop on failures; never hide a failed stage behind
a successful earlier one.

After each verified publication, obtain a fresh clean checkout at the current
remote main SHA in a new cloud directory before preparing the next input. Reuse
the isolated interpreter if suitable. A plugin ref update does not advance the
previous checkout's HEAD: do not reuse its stale base SHA or include the previous
input's changes in another commit. Do not reset or discard a failed checkout's
recovery data.

Return a concise Chinese report with announcement date, all three class counts,
output links, executed test count and exit codes, commit SHA, and separate
PASS/FAIL/BLOCKED/PENDING results for cloud startup, current-input capture,
real report generation,
GitHub writeback, Pages deployment, and Issue notification. The first scheduled
production run must explicitly give this full acceptance result. If no new
input is available, state that end-to-end publication remains untested for
that run. Subsequent runs notify on successful publication, real failure, or
required user action; unchanged/no-new-input checks should remain quiet where
the platform supports that behavior. Do not create follow-up schedules.
