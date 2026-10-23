Use `AGENTS.md` as the repository-wide evidence contract.

Before implementation, read `policy/project-state.json` and the documents under `docs/`.
Treat `PASS`, `GAP`, `UNKNOWN_EXTERNAL`, and `NOT_APPLICABLE` as distinct states.
Do not claim tests, builds, checks, releases, maturity levels, or security controls passed unless the relevant evidence was actually executed or observed.
When a first release or maturity-relevant change is observed, run `python scripts/harness.py` and report newly applicable gaps before declaring the task complete.
