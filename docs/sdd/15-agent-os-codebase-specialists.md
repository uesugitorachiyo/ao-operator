# 15 - Agent OS Codebase Map And Specialists

Classification: MODERATE
Shape: greenfield

## Scope

This slice adds a deterministic codebase surface mapper for Agent OS specialist
planning. It records which AO Operator surfaces exist and recommends specialist
roles for later capability validation. It does not dispatch AO providers.

## Surfaces

The mapper records:

- runtime scripts
- tests
- SDD docs
- agent contracts
- skills

The core required surfaces are runtime scripts, tests, and SDD docs.

## Specialist Plan

The first specialist set is intentionally conservative:

- engineering-manager
- release-manager
- docs-release
- QA
- capability-validator

These are recommendations only. Future slices must add role contracts and
capability validation before any new specialist participates in AO dispatch.

## Negative Constraints

- MUST NOT dispatch AO providers from this slice.
- MUST NOT infer sensitive implementation details from provider transcripts.
- MUST NOT treat specialist recommendations as executable role contracts.
- MUST NOT fail when optional agent or skill surfaces are absent.

## Verification

```bash
python3 -m pytest -q tests/test_agent_os_codebase_map.py
python3 scripts/agent_os_codebase_map.py --write-output --json
```

## Acceptance Criteria

- Codebase map returns `PASS` when runtime scripts, tests, and SDD docs exist.
- Map output records `dispatch_authorized=false`.
- Map output records `live_providers_run=false`.
- Map output recommends a specialist set for the next capability-validation
  slice.
