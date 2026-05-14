# 14 - Agent OS Mission Router And State

Classification: MODERATE
Shape: greenfield

## Scope

This slice starts the Agent OS implementation with a local, deterministic
mission router and state snapshot. It does not dispatch AO providers and does
not change existing AO Operator runtime behavior.

## Router Contract

The router accepts a task brief and optional route labels. It returns:

- classification
- shape
- routes
- shape-gate blocker state
- required verification
- dispatch authorization
- next safe command

Route labels are:

- `fast`
- `quick`
- `phase`
- `live-provider`
- `remote-worker`
- `security-sensitive`
- `frontend`
- `release`

`live-provider` always blocks until an explicit approval artifact and provider
budget evidence exist.

## State Contract

The state snapshot records the active lane, route output, dispatch state,
blockers, next safe command, and required Agent OS project artifacts:

- `PROJECT.md`
- `REQUIREMENTS.md`
- `ROADMAP.md`
- `STATE.md`
- `DECISIONS.md`
- `LEARNINGS.md`

## Negative Constraints

- MUST NOT dispatch AO providers from this slice.
- MUST NOT change existing AO Operator runtime routing behavior.
- MUST NOT authorize live-provider work without explicit approval evidence.
- MUST NOT write project state outside a caller-selected `--write-state` path.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_router.py
python3 scripts/agent_os_router.py \
  --brief examples/agent-os/mission-router-state-brief.md \
  --label release \
  --state-version v1 \
  --write-state run-artifacts/remote-transfer-v2-stress-live/agent-os-mission-router-state.json \
  --json
```

## Acceptance Criteria

- Router tests pass.
- Sample state evidence records `schema=ao-operator/agent-os-state/v1`.
- Sample state evidence records `live_providers_run=false`.
- `live-provider` route tests prove dispatch remains blocked without approval.
