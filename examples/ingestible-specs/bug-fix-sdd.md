# Bug Fix SDD: Empty Input Validation

## Goal

Fix a CLI command so empty input returns a clear validation error instead of
continuing with a confusing default.

## User Impact

Users currently cannot tell whether the command accepted an empty value or
silently substituted a default. The fix should make the failure explicit.

## Scope

- Detect empty or whitespace-only input.
- Return a clear message: `input cannot be empty`.
- Preserve existing behavior for non-empty input.
- Add or update a regression test.

## Non-Goals

- No command-line framework migration.
- No new configuration file.
- No broad refactor.
- No provider API keys.

## Role Expectations

- Intake clarifies the exact failure boundary.
- Planner proposes the smallest implementation and test proof.
- Implementer changes only the validation path.
- Reviewer checks non-empty input behavior and error wording.
- Evaluator-closer accepts only if the test evidence is named.

## Acceptance Criteria

- Empty input fails with `input cannot be empty`.
- Whitespace-only input fails the same way.
- Non-empty input behavior is unchanged.
- Final evidence names the changed file and test command.
