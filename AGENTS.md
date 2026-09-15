# Repository guidance

This repository creates an English personalized arXiv math.DS digest. Python
prepares metadata and validates/renders reports; Codex writes the analysis locally.
GitHub Actions captures official RSS into immutable, validated `data/inbox/`
inputs. Local `src.prepare_run` reads the synced inbox without HTTP or a network
fallback. Missing/stale/corrupt input is an error, never an empty digest. Process
unfinished inputs in announcement order; report dates come from the feed, not
the day a backlog happens to be processed. Mark inputs processed only after
successful finalization, together with the existing seen-paper state.
No model API, SDK, AI API credential, or direct email credential belongs in this pipeline.

For a daily digest run, read and follow [DAILY_AUTOMATION.md](DAILY_AUTOMATION.md)
and the research profile in `config.yaml` before analyzing anything. Preserve the
existing English report templates. Use `tests/fixtures/math_ds.xml` for all tests.
Run `pytest -q` after pipeline changes.
Fixtures and demonstrations require isolated temporary data/site/inbox paths;
never place synthetic inputs in production. Validate arXiv URL/ID relationships
locally, without fetching paper links. Cloud capture is scheduled for weekdays
11:15 Europe/Warsaw; the local task instructions target weekdays 12:00 in that
timezone. Maintenance does not change or trigger the local task without user authorization.

New daily reports generate HTML and backend JSON only. The permanent homepage
lists all dates; dated HTML is the primary public report. Preserve existing
legacy PDF/Markdown files exactly, and link them only where they already exist.
Never regenerate those formats during finalization or HTML rebuilding.

Base mathematical claims only on supplied titles/abstracts. Preserve hypotheses,
qualifications, notation, and the distinction between proven results, conjectures,
examples, and numerical evidence. Never invent missing information.
Use only `\(...\)` for inline and `\[...\]` for display mathematics in authored
prose; check paired delimiters and do not put normally rendered math in code blocks.

Work inside this repository. Do not commit, push, create secrets, or create a
schedule during maintenance unless the current user request authorizes it.
The future explicitly authorized daily task follows the publication procedure
in DAILY_AUTOMATION.md only after validation and inspection succeed.
Its fixed commit message is `Add daily math.DS digest`, matching the existing
project rule. Do not broaden Git rules or global permissions to resolve failures.
