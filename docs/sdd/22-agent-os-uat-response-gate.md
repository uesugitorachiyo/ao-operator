# 22 - Agent OS UAT Response Gate

Classification: MODERATE
Shape: greenfield

## Scope

This slice adds the human UAT response gate. It generates a response template
from pending UAT items and evaluates whether complete accepted human responses
exist. It only authorizes closure when every required UAT item is explicitly
accepted with responder, response, and timestamp fields.

## Response Contract

The gate lives at `scripts/agent_os_uat_response_gate.py`.

It reads:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-state.json`
- `run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-responses.json`

It emits:

- `run-artifacts/remote-transfer-v2-stress-live/agent-os-uat-response-gate.json`

The response template uses schema
`ao-operator/agent-os-uat-responses/v1`.

## Negative Constraints

- MUST NOT fabricate human acceptance.
- MUST NOT authorize closure while any response is missing, pending, rejected,
  or incomplete.
- MUST NOT dispatch AO providers.
- MUST NOT hide rejected UAT responses.
- MUST NOT mutate runtime role behavior.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_uat_response_gate.py
python3 scripts/agent_os_uat_response_gate.py --write-template --write-output --json
```

## Acceptance Criteria

- Response gate emits schema `ao-operator/agent-os-uat-response-gate/v1`.
- Response template is generated when missing.
- Missing responses keep `closure_authorized=false`.
- Rejected responses keep `closure_authorized=false`.
- Complete accepted responses allow `closure_authorized=true`.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
