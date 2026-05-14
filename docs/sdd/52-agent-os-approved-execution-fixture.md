# Agent OS Approved Execution Fixture

## Classification

- Size: MODERATE
- Shape: greenfield
- Live provider: false
- Dispatch authorized: false

## Goal

Provide a deterministic, provider-free fixture for the Agent OS approved
execution happy path. The fixture exercises approval validation, postrun routing,
evaluator closure, and accepted-execution commit guarding without running AO or
calling any model provider.

## Negative Constraints

- Do not run `ao run`.
- Do not set top-level `dispatch_authorized=true`.
- Do not set top-level `live_providers_run=true`.
- Do not allow fixture output to be committed as live success evidence.
- Do not treat `fixture_only=true` execution reports as accepted production
  evidence.

## Contract

The fixture emits:

- `schema=ao-operator/agent-os-approved-execution-fixture/v1`
- `fixture_only=true`
- `dispatch_authorized=false`
- `live_providers_run=false`
- `commit_success_evidence_allowed=false`
- component results for approval validation, execution report, postrun route,
  evaluator closure, and commit guard

The commit guard must reject accepted-route evidence when the execution report
is fixture-only or did not run live providers.

## Verification

```bash
python3 scripts/check_agent_os_approved_execution_fixture.py --write-output --json
python3 -m pytest -q tests/test_agent_os_approved_execution_fixture.py tests/test_agent_os_execution_readiness.py
python3 scripts/validate_factory.py --json
```
