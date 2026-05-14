# Intake Artifact

Do not dispatch implementers from a loose prompt. Convert intent into a bounded
intake artifact first.

## Core Fields

Every intake must include:

- Outcome: one sentence describing the user-visible end state.
- Scope: in-scope and out-of-scope bullets.
- Stack/context: relevant repos, files, commands, models, ports, and runtime.
- `Classification:` TRIVIAL, MODERATE, or COMPLEX.
- `Shape:` `greenfield`, `bug-fix`, or `refactor`.
- Success criteria tied to evidence, not claims.
- Constraints: explicit `Do not ...` negative constraints.
- Sensitive fields touched: auth files, API keys, transcripts, secrets, user
  data, provider stderr, path names, or generated artifacts.
- Trigger hints for reviewers: security, UX, DB, performance, build, docs, MCP.
- Verification: deterministic commands or review oracles that prove completion.
- Refactor evidence: for non-trivial `Shape: refactor` work, include
  `python scripts/code_smell_analyzer.py <paths> --json`
  output or explain why code-smell analysis is not applicable.

## Slices

Include a slice table with `reads:` and `writes:` when more than one worker could
be used. Single-worker work may say why fan-out is not appropriate.

Each slice should state:

- owner role,
- reads,
- writes,
- verification,
- dependencies,
- rollback or integration notes when relevant.

## Ready Checklist

Intake is ready only when:

- `Shape` and `Classification` are explicit,
- every success criterion has a verification route,
- negative constraints block likely scope creep,
- slices declare `reads` and `writes` or the task is single-worker,
- sensitive fields and trigger hints are listed,
- open questions are answered or marked as blockers.
