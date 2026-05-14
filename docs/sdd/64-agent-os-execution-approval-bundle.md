# 64 - Agent OS Execution Approval Bundle

Classification: MODERATE
Shape: greenfield

## Scope

This slice adds a template-only approval bundle for Agent OS RunSpec execution.
It packages the current approval gate, RunSpec SHA-256 lock, execution command,
approval target path, and an operator-editable approval template. It does not
create a valid approval by itself.

## Contract

The generator lives at `scripts/generate_agent_os_approval_bundle.py`.

It reads:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-gate.json`

It emits:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-approval-bundle.json`

The emitted `approval_template` must include:

- `schema=ao-operator/agent-os-runspec-execution-approval/v1`
- `approved=false`
- blank `operator`
- blank `accepted_risk`
- `approved_at`
- `expires_at`
- `runspec_path`
- `runspec_sha256`
- `task_count`

## Negative Constraints

- MUST NOT run AO.
- MUST NOT dispatch providers.
- MUST NOT write the real approval file.
- MUST NOT emit `approved=true`.
- MUST NOT generate a bundle when the approval gate lacks a SHA-256 RunSpec
  lock.

## Verification

```bash
python3 -m pytest -q tests/test_generate_agent_os_approval_bundle.py
python3 scripts/generate_agent_os_approval_bundle.py --write-output --json
```

## Acceptance Criteria

- Approval bundle emits schema `ao-operator/agent-os-execution-approval-bundle/v1`.
- Template carries current `runspec_sha256`, `runspec_path`, and `task_count`.
- Template includes operator and expiry fields.
- Template remains invalid until an operator explicitly fills it and sets
  `approved=true`.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
