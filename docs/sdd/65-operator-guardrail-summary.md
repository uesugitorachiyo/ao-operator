# Operator Guardrail Summary

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Provide one operator-readable JSON report that aggregates the current
post-acceptance guardrails:

- Agent OS operator cockpit
- remote transfer hardening
- public-release AST/security surface
- no-provider DAST readiness
- security SDLC roadmap
- threat model/data-flow gate
- manual penetration-test gate
- host-key evidence gate
- manual pentest report classifier
- supply-chain gate
- resource/performance gate
- Agent OS approval bundle
- release readiness
- Agent OS no-provider execution rehearsal
- Agent OS approval lifecycle
- Agent OS approval cleanup
- Agent OS approved launch proof
- Agent OS RunSpec DAG edge coverage
- Agent OS RunSpec YAML DAG parity
- Agent OS RunSpec YAML semantic parity

The report must preserve the execution boundary: it is a status view, not an
execution command.

## Contract

`scripts/check_operator_guardrail_summary.py` emits
`ao-operator/operator-guardrail-summary/v1`.

Required behavior:

- Each input report must exist, use the expected schema, and have `verdict=PASS`.
- Every input report must keep `dispatch_authorized=false`.
- Every input report must keep `live_providers_run=false`.
- Release readiness must keep `ship_ready=true`.
- The no-provider rehearsal must keep `refused_without_approval=true` and
  `would_run_provider=false`.
- The approval lifecycle state and usability must be surfaced.
- Approval cleanup state must be surfaced.
- Approved launch proof must show `PLAN` without provider dispatch.
- RunSpec DAG edge coverage must show role graph alignment and fail-closed
  mutation cases.
- RunSpec YAML DAG parity must show YAML-to-renderer and YAML-to-role-graph
  alignment with fail-closed mutation cases.
- RunSpec YAML semantic parity must show all six task fields aligned and
  fail-closed mutation cases for provider, prompt, workspace, policy, kind,
  and dispatchAuthorized drift.

## Negative Constraints

- Do not create or modify execution approval files.
- Do not run AO.
- Do not dispatch provider CLIs.
- Do not treat the summary as proof of live execution.
- Do not omit approval lifecycle, cleanup, or positive-path proof state.

## Verification

```bash
python3 -m pytest -q tests/test_check_operator_guardrail_summary.py
python3 scripts/check_operator_guardrail_summary.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/operator-guardrail-summary.json
```
