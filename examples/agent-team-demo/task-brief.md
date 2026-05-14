# Agent Team Demo Brief

## Goal

Demonstrate how AO Operator turns a small coding request into a repeatable
agent-team workflow.

## Scenario

A small CLI tool has a user-facing bug: when the input is empty, it should
return a clear validation message instead of continuing with a confusing
default. The implementation details are intentionally abstract because this
demo focuses on the operator workflow, not the application code.

## Desired Agent Team

- Intake clarifies the failure and the acceptance boundary.
- Planner proposes the narrowest fix and the test proof.
- Implementer makes the minimal patch.
- Reviewer checks risk and missed cases.
- Evaluator-closer decides whether the evidence is enough.

## Acceptance Criteria

- Empty input is rejected with a clear message.
- Non-empty input behavior is unchanged.
- The final report names the file changed, the test command, and the result.
- The run leaves inspectable status artifacts under `run-artifacts/<slug>/`.

## Non-Goals

- No new framework.
- No hosted service.
- No provider API keys.
- No broad refactor.
