# Agent OS Post-Approval Cleanup Route

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that a simulated accepted postrun route can be followed by approval
cleanup and a return to `approval_state=ABSENT`, without dispatching providers
or writing a real repository approval file.

## Contract

`scripts/check_agent_os_post_approval_cleanup_route.py` emits
`ao-operator/agent-os-post-approval-cleanup-route/v1`.

The proof must:

- build an isolated fixture from the current RunSpec, approval gate, and bundle
- materialize approval only inside the fixture
- seed a simulated accepted execution report
- route postrun state to `ACCEPTED`
- force cleanup of the fixture approval file
- verify lifecycle returns to `ABSENT`
- append materialization and cleanup events to fixture audit history
- keep `dispatch_authorized=false`
- keep `live_providers_run=false`

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not write the real repository approval file.
- Do not treat simulated accepted execution as live acceptance evidence.

## Verification

```bash
python3 -m pytest -q tests/test_check_agent_os_post_approval_cleanup_route.py
python3 scripts/check_agent_os_post_approval_cleanup_route.py --write-output --json
```

## Evidence

```text
run-artifacts/remote-transfer-v2-stress-live/agent-os-post-approval-cleanup-route.json
```
