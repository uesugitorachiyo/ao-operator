# 16 - Agent OS Capability And Skill Validation

Classification: MODERATE
Shape: greenfield

## Scope

This slice adds the first Agent OS capability contract and validator. It maps
existing AO Operator core roles to capabilities, allowed tools, reads, writes,
risk level, dispatch mode, provider boundary, verification command, and
required skills. Specialist recommendations remain non-executable.

## Capability Contract

The contract lives at `docs/contracts/ao-operator-agent-capabilities.json`.

Core role entries must declare:

- `id`
- `contract`
- `capabilities`
- `allowed_tools`
- `reads`
- `writes`
- `risk_level`
- `dispatch_mode`
- `provider_boundary`
- `verification`
- `required_skills`

Specialist entries must declare capabilities and allowed tools but must keep
`executable=false`.

## Negative Constraints

- MUST NOT dispatch AO providers from capability validation.
- MUST NOT activate specialists without explicit executable role contracts.
- MUST NOT grant provider auth access through capability metadata.
- MUST NOT bypass existing AO Operator provider and approval gates.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_capability_validator.py
python3 scripts/agent_os_capability_validator.py --write-output --json
```

## Acceptance Criteria

- Capability contract validates every existing core role TOML file.
- Required local skills exist for every role that declares them.
- Specialist recommendations remain non-executable.
- Validation report records `dispatch_authorized=false`.
- Validation report records `live_providers_run=false`.
