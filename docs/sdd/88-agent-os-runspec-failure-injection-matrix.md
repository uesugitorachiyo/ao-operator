# 88 - Agent OS RunSpec Failure-Injection Matrix

## Classification

- Size: MODERATE
- Shape: greenfield
- Lane: Agent OS execution safety hardening

## Objective

Exercise provider-free failure-injection cases for Agent OS RunSpec validation,
approval locking, prompt integrity, dispatch flags, provider profiles, and state
baseline coupling before any future live execution approval lane.

## Scope

The gate lives at `scripts/check_agent_os_runspec_failure_injection_matrix.py`.

It writes:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-failure-injection-matrix.json`

## Required Behavior

- Validate a baseline generated RunSpec fixture.
- Refuse stale approval hashes.
- Refuse missing prompt files.
- Refuse mutated `dispatchAuthorized=true` task specs.
- Refuse provider profile mismatches.
- Refuse unsupported task providers.
- Refuse missing state v2 baselines.
- Keep the matrix artifact non-dispatching.

## Negative Constraints

- MUST NOT run AO.
- MUST NOT run provider CLIs.
- MUST NOT materialize a real repo approval file.
- MUST NOT run a live execution launcher.
- MUST NOT convert refusal cases into warnings.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_runspec_failure_injection_matrix.py
python3 scripts/check_agent_os_runspec_failure_injection_matrix.py --write-output --json
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Gate verdict is `PASS`.
- `case_count=7`.
- Baseline case validates with `PASS`.
- Stale approval hash case is `REFUSED`.
- Prompt, dispatch flag, provider profile, unsupported provider, and missing
  state baseline cases are `FAIL`.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
