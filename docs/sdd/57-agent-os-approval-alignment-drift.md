# 57 - Agent OS Approval Alignment Drift

## Classification

- Size: MODERATE
- Shape: greenfield
- Lane: Agent OS execution safety

## Objective

Fail closed when Agent OS approval, execution, or fixture artifacts lose the
provider-profile alignment fields required before execution approval.

## Scope

The checker lives at `scripts/check_agent_os_approval_alignment_drift.py`.
It reads committed Agent OS approval/execution artifacts and verifies each one
preserves:

- `provider_profile`
- `provider_profile_checked=true`
- `provider_profile_matches=true`
- empty `provider_mismatches`
- `dispatch_authorized=false`
- `live_providers_run=false`

It writes
`run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-alignment-drift.json`.

## Negative Constraints

- MUST NOT authorize dispatch.
- MUST NOT run AO.
- MUST NOT run provider CLIs.
- MUST NOT accept missing provider alignment as an implicit default.

## Verification

```bash
python3 scripts/check_agent_os_approval_alignment_drift.py --write-output --json
python3 -m pytest -q tests/test_agent_os_approval_alignment_drift.py
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Drift report verdict is `PASS`.
- Every checked artifact has provider alignment fields.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
