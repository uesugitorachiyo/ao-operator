# Financial Citation Audit SDD: Earnings Note Review

## Goal

Review a synthetic earnings-note draft and verify that every material claim has
a matching source citation.

## Public Wedge

This is not "AI for finance." It is a citation and compliance review workflow
with a signed paper trail.

## Scope

- Read a public or synthetic source pack.
- Extract material claims from the draft.
- Match each claim to a citation.
- Flag unsupported claims.
- Stage a reviewer-facing report.

## Non-Goals

- No trading.
- No investment advice.
- No paid connector credentials.
- No claim that the output is compliant.

## Role Expectations

- Intake records source-pack assumptions.
- Planner maps claim extraction and citation checks.
- Implementer produces deterministic audit output.
- Reviewer acts adversarially and searches for unsupported claims.
- Evaluator-closer accepts only with citation evidence.

## Acceptance Criteria

- Every material claim is marked supported or unsupported.
- Unsupported claims include a reason.
- The final report names the source pack.
- The workflow can run without provider API keys.
