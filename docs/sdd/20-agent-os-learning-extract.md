# 20 - Agent OS Learning Extraction

Classification: MODERATE
Shape: greenfield

## Scope

This slice extracts durable Agent OS process learnings from UAT state while UAT
is still pending. It records lessons, negative learnings, role-level evidence
needs, open blockers, and next actions. It does not authorize closure.

## Learning Contract

The extractor lives at `scripts/agent_os_learning_extract.py`.

It reads `run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-state.json`
and emits
`run-artifacts/remote-transfer-v2-stress-live/agent-os-learning-extract.json`.

The report must include:

- pending UAT count
- open blockers
- lessons
- negative learnings
- role-level learning keyed by role id
- next actions

## Negative Constraints

- MUST NOT authorize closure while UAT remains pending.
- MUST NOT treat local validation as human acceptance.
- MUST NOT dispatch AO providers from learning extraction.
- MUST NOT hide open blockers.
- MUST NOT mutate `AGENTS.md` or inject generated context.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_learning_extract.py
python3 scripts/agent_os_learning_extract.py --write-output --json
```

## Acceptance Criteria

- Learning report emits schema `ao-operator/agent-os-learning-extract/v1`.
- Pending UAT count is recorded.
- Open UAT blockers are preserved.
- Role-level learning records high-risk closure needs.
- `closure_authorized=false`.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
