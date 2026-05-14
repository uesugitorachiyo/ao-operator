# SDD 77: Agent OS Approval Identity Signature

## Goal

Prove an actual local identity-bound signing flow for approval bundles without
committing private keys or dispatching execution.

## Scope

- Use `ssh-keygen -Y sign` and `ssh-keygen -Y verify` in an isolated fixture.
- Generate a temporary Ed25519 operator key only inside the fixture.
- Verify the approval bundle signature and record public fingerprint evidence.
- Do not commit private key material, signatures, or approval files from the
  fixture.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not write real approval files.
- Do not commit private keys or private key paths.

## Verification

```bash
python3 scripts/check_agent_os_approval_identity_signature.py --write-output --json
python3 -m pytest -q tests/test_check_agent_os_approval_identity_signature.py
```
