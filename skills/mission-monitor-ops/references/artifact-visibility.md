# Artifact Visibility

When debugging Specs panel behavior, inspect:

- `docs/specs/*-spec.md` for `**Classification:**` and `**Shape:**`,
- `run-artifacts/<slug>-status.md` for `## <role>` headings and STATUS blocks,
- `docs/evaluations/<slug>-evaluation.md` for terminal verdict,
- `run-artifacts/LEDGER.md` for ledger verdict overlay.

For workflow visibility issues, confirm that the dashboard maps each artifact to
the right slug and repo root. Missing UI state should be fixed by parser or
projection changes, not by copying private data into status files.
