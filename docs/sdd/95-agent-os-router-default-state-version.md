# 95 - Agent OS Router Default State Version

## Classification

- Size: MODERATE
- Shape: refactor
- Lane: Agent OS architecture implementation

## Objective

Promote the Agent OS mission router CLI default for `--state-version` from
`v1` to `v2`, while keeping every existing v1 caller working through an
explicit `--state-version v1` opt-out. Lock the default with a fail-closed
gate so future refactors cannot silently revert.

## Scope

`scripts/check_agent_os_router_default_state_version.py` writes:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-router-default-state-version.json`

The gate reads `scripts/agent_os_router.py` source to assert the argparse
default for `--state-version`, then runs three deterministic CLI invocations
(default / explicit `v1` / explicit `v2`) against the existing architecture
readiness artifact and verifies the schema each one writes.

## Required Behavior

- `argparse_default` MUST be `"v2"` in `scripts/agent_os_router.py`.
- Default invocation (no `--state-version`) MUST emit
  `ao-operator/agent-os-state/v2` with `architecture_ready=true` whenever the
  architecture readiness gate is PASS.
- Explicit `--state-version v1` MUST still emit
  `ao-operator/agent-os-state/v1` (back-compat path).
- Explicit `--state-version v2` MUST match the default invocation's schema.
- Gate output MUST keep `dispatch_authorized=false` and
  `live_providers_run=false`.
- Gate MUST fail closed when any case observes a different schema or a
  non-zero exit code.

## Negative Constraints

- MUST NOT run AO.
- MUST NOT run provider CLIs.
- MUST NOT authorize dispatch from this gate.
- MUST NOT silently fall back to v1 when v2 prerequisites are missing.
- MUST NOT remove the `--state-version v1` code path before downstream
  callers (operator slice 40, SDD 14 verification example) migrate.

## Verification

```bash
python3 -m pytest -q tests/test_check_agent_os_router_default_state_version.py
python3 scripts/check_agent_os_router_default_state_version.py --write-output --json
python3 scripts/validate_operator_slices.py examples/remote-transfer-v2-stress/operator-slices.json --json
python3 scripts/validate_factory.py --json
```

## Acceptance Criteria

- Gate verdict is `PASS`.
- `argparse_default="v2"`.
- `case_count=3`.
- All three cases observe `PASS` and the expected schema.
- `dispatch_authorized=false` and `live_providers_run=false`.
- Existing v1 callers (operator slice `40`, SDD 14 verification command) are
  pinned with explicit `--state-version v1`.
