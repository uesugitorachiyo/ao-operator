# 17 - Agent OS Phase Compiler And Verification Matrix

Classification: MODERATE
Shape: greenfield

## Scope

This slice adds a deterministic Agent OS phase compiler. It reads the validated
role capability contract and the committed Agent OS state-v2 baseline, then
emits a local-only phase plan plus verification matrix. The compiler does not
dispatch AO providers and does not make specialist roles executable.

## Compiler Contract

The compiler lives at `scripts/agent_os_phase_compiler.py`.

It reads `docs/contracts/ao-operator-agent-capabilities.json` plus
`run-artifacts/remote-transfer-v2-stress-live/agent-os-state-v2.json` and emits
`run-artifacts/remote-transfer-v2-stress-live/agent-os-phase-compiler.json`.

The emitted report must include:

- `phase_plan.steps` ordered through the core AO Operator role chain.
- `phase_plan.state_schema_version=ao-operator/agent-os-state/v2`.
- `state_baseline` proving the compiler used a PASS state-v2 snapshot with the
  expected role graph schema and dispatch disabled.
- Per-step dependencies, reads, writes, capabilities, risk level, dispatch
  mode, and exit gate.
- `verification_matrix.required_commands` keyed by role id.
- `verification_matrix.risk_gates` with closure evidence required for high-risk
  roles.
- `verification_matrix.specialist_gates` proving specialists remain behind
  future role-contract activation gates.

## Negative Constraints

- MUST NOT dispatch AO providers from phase compilation.
- MUST NOT authorize live provider runs.
- MUST NOT activate specialist roles.
- MUST NOT treat a compiled plan as an executable AO RunSpec.
- MUST NOT bypass existing AO Operator approval gates.
- MUST fail closed if the state-v2 baseline is missing, unsafe, or dispatch
  authorized.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_phase_compiler.py
python3 scripts/agent_os_phase_compiler.py --write-output --json
```

## Acceptance Criteria

- Compiler emits schema `ao-operator/agent-os-phase-compiler/v1`.
- Compiler preserves `dispatch_authorized=false`.
- Compiler preserves `live_providers_run=false`.
- Phase plan includes required core roles in dependency order.
- Phase plan records `state_schema_version=ao-operator/agent-os-state/v2`.
- State baseline records `schema=ao-operator/agent-os-state/v2`,
  `role_graph_schema=ao-operator/agent-os-role-graph/v1`,
  `dispatch_authorized=false`, and `live_providers_run=false`.
- Verification matrix includes every core role verification command.
- High-risk roles require closure evidence.
- Specialist entries remain non-executable through activation gates.
