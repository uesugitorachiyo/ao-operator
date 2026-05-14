# Status

Store durable task status and role handoff summaries here.

## Generated Artifact Hygiene

Factory runs generate coordinated artifacts under `docs/specs/`, `docs/plans/`,
`run-artifacts/`, and `docs/evaluations/`. Commit a run only when its evidence is
intentionally part of the repository baseline.

Use `python3 scripts/artifact_hygiene.py` before committing after live runs. The
report classifies untracked generated artifacts as:

- `PRESERVE_CANDIDATE`: accepted evaluation plus matching spec, plan, and status
  artifacts. These can be committed when they are part of the baseline or a PR's
  evidence.
- `ARCHIVE_OR_DROP`: rejected or blocked evaluations. Keep locally for debugging,
  archive deliberately if the failure is historically important, or remove after
  the accepted successor is recorded.
- `REVIEW_INCOMPLETE`: missing evaluation verdict or missing one of the core
  artifact families. Do not commit until the run is completed or explained.

`python3 scripts/artifact_hygiene.py --strict` exits non-zero when untracked
Factory artifacts are present and is suitable as a local pre-PR guard.
`scripts/verify_closure.py` runs that strict guard automatically when
`scripts/artifact_hygiene.py` is present.

Use `python3 scripts/pr_ready.py` before opening or merging a PR. It runs the
local merge gate: py_compile, scaffold validation, artifact hygiene strict mode,
pytest, and closure verification.

GitHub Actions should use `python3 scripts/pr_ready.py --ci --json`. CI mode
runs the deterministic subset: py_compile, scaffold validation, artifact hygiene
strict mode, and pytest. It deliberately skips closure verification because that
gate checks local OAuth, Codex auth, and AO runtime state.
