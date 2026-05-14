# SDD 78: Agent OS Approval Revocation Apply Proof

## Goal

Prove `--apply --force` approval revocation behavior in an isolated fixture so
real approval files can be revoked confidently when operators choose to do so.

## Scope

- Materialize a fixture-only approval file.
- Apply revocation inside the fixture.
- Verify the approval file is absent after revocation.
- Verify the revocation log is compact and omits accepted-risk text and nested
  approval payloads.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not mutate the real repository approval file.
- Do not log full approval payloads.

## Verification

```bash
python3 scripts/check_agent_os_approval_revocation_apply_proof.py --write-output --json
python3 -m pytest -q tests/test_check_agent_os_approval_revocation_apply_proof.py
```
