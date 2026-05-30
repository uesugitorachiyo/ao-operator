# Slices And Sensitive Fields

Slices are dataflow, not just task labels.

Use `spec_forge slice-plan` when a MODERATE or COMPLEX contract has weak or
missing slices. The command proposes deterministic slices from AC `file_hints`,
strict-glob metadata, and AC dependencies; it is advisory until the final
contract passes lint and dispatch gate.

## Slice Discipline

- `writes` must not overlap across parallel slices.
- A slice that reads another slice's writes must declare `depends_on`.
- Files matching target `strict_globs` should force a single-worker path.
- Every slice must reference at least one AC.
- For non-trivial refactors, use code-smell analyzer evidence to justify slice
  boundaries when Python files are in scope.

```bash
python scripts/code_smell_analyzer.py <paths> --json
```

## Sensitive Fields

Declare every sensitive surface the work may touch, including:

- auth files,
- API keys or OAuth material,
- transcripts,
- secrets,
- user data,
- provider stderr,
- path names,
- generated artifacts.

## Trigger Hints

Name reviewer triggers explicitly: security, UX, DB, performance, build, docs,
MCP, release, or provider/runtime boundaries.
