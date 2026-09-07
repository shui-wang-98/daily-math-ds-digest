# Repository guidance

This repository creates an English personalized arXiv math.DS digest. Python
prepares metadata and validates/renders reports; Codex writes the analysis locally.
No model API, SDK, AI API credential, or direct email credential belongs in this pipeline.

For a daily digest run, read and follow [DAILY_AUTOMATION.md](DAILY_AUTOMATION.md)
and the research profile in `config.yaml` before analyzing anything. Preserve the
existing English report templates. Use `tests/fixtures/math_ds.xml` for all tests.
Run `pytest -q` after pipeline changes.

Base mathematical claims only on supplied titles/abstracts. Preserve hypotheses,
qualifications, notation, and the distinction between proven results, conjectures,
examples, and numerical evidence. Never invent missing information.
Use only `\(...\)` for inline and `\[...\]` for display mathematics in authored
prose; check paired delimiters and do not put normally rendered math in code blocks.

Work inside this repository. Do not commit, push, create secrets, or create a
schedule during maintenance unless the current user request authorizes it.
The future explicitly authorized daily task follows the publication procedure
in DAILY_AUTOMATION.md only after validation and inspection succeed.
