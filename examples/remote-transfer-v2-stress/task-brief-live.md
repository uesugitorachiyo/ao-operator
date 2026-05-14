# Remote Transfer v2 Bounded Live Stress Task Brief

Use AO Operator to run a complex bounded live AO-backed provider stress
profile for Remote Transfer v2.

Shape it as greenfield.

## Goal

Materialize and run a small live AO Operator topology before attempting any
wider provider fan-out: 50 implementation factories,
50 reviewer branches, and the standard Spec Forge, Ralph Loop,
integrator, and evaluator gates.

This is the live counterpart to the 1000-slice dry-run stress fixture. It
exists to prove AO Runtime provider execution, role artifacts, event
capture, and closure behavior without exceeding provider limits.

## Product Scope

The generated plan covers the first 50 Remote Transfer v2 work
domains from the stress contract.

## Constraints

- Use OAuth CLI providers only.
- Do not configure `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.
- Do not read or transfer provider auth files.
- Do not run the 1000-slice stress topology in live mode.
- Do not raise the live slice count without operator approval.
- Every role must return Result, Artifact, Evidence, Concerns, and Blocker.

## Acceptance Criteria

- AO Operator materializes all 107 bounded live topology tasks.
- The generated RunSpec contains every bounded live factory and reviewer task.
- Prompt directory exactly matches the bounded topology task IDs.
- AO events capture a real run id, command exit, completion state, and
  provider failure evidence when failures occur.
- `validate_factory.py` and `validate_intake.py` both return PASS before
  live dispatch.
