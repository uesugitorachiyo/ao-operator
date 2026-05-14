# Agent OS Approval Materialization

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Add an explicit approval-file materializer for Agent OS RunSpec execution. The
default mode is a dry-run report. Writing the approval file requires deliberate
operator input and an unchanged RunSpec hash.

## Contract

`scripts/materialize_agent_os_approval.py` emits
`ao-operator/agent-os-approval-materialization/v1`.

Default behavior:

- Validate the approval bundle and approval gate.
- Recompute the current RunSpec SHA-256.
- Report the approval payload that would be written.
- Keep `approval_file_written=false`.
- Keep `approval_valid=false`.
- Keep `dispatch_authorized=false`.
- Keep `live_providers_run=false`.

Write behavior requires all of:

- `--write-approval-file`
- `--approved`
- non-empty `--operator`
- non-empty `--accepted-risk`
- current RunSpec SHA-256 matching the approval gate and bundle

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not write approval files by default.
- Do not write approval files after RunSpec hash drift.
- Do not overwrite an existing approval file unless `--overwrite` is explicit.

## Verification

```bash
python3 -m pytest -q tests/test_materialize_agent_os_approval.py
python3 scripts/materialize_agent_os_approval.py --write-output --json
```

## Evidence

The durable dry-run status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/agent-os-approval-materialization.json
```
