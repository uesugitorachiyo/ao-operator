# Agent OS Approved Launch Proof

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove the positive approval path without writing a real repository approval file
or dispatching providers. The proof must show that the launcher is blocked when
approval is absent, then reaches `PLAN` after an approval is materialized inside
an isolated fixture.

## Contract

`scripts/check_agent_os_approved_launch_proof.py` emits
`ao-operator/agent-os-approved-launch-proof/v1`.

The proof must:

- copy the current Agent OS RunSpec, approval gate, and approval bundle into an
  isolated temp fixture
- validate that absent approval keeps the launcher `BLOCKED`
- materialize an approval file inside only the fixture
- validate the materialized approval
- re-run the approval-only launcher without `--execute`
- require the final launcher verdict to be `PLAN`
- keep `would_run_provider=false`
- keep `dispatch_authorized=false`
- keep `live_providers_run=false`

## Negative Constraints

- Do not write the real repository approval file.
- Do not run AO.
- Do not dispatch provider CLIs.
- Do not treat `PLAN` as accepted execution evidence.
- Do not reuse a fixture directory unless it carries the proof marker.

## Verification

```bash
python3 -m pytest -q tests/test_check_agent_os_approved_launch_proof.py
python3 scripts/check_agent_os_approved_launch_proof.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/agent-os-approved-launch-proof.json
```
