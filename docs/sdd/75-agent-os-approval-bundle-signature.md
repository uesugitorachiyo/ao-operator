# SDD 75: Agent OS Approval Bundle Signature

## Goal

Add tamper-evident approval bundle verification before any approval
materialization path can be trusted.

## Scope

- Hash the canonical approval bundle JSON.
- Store the digest in a sidecar signature artifact.
- Verify later runs detect approval bundle tampering.
- Keep the signature profile local and no-secret: this is integrity evidence,
  not an operator identity signature.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not write approval files.
- Do not claim identity-bound cryptographic signing without a real private key
  flow.

## Verification

```bash
python3 scripts/check_agent_os_approval_bundle_signature.py --write-signature --write-output --json
python3 -m pytest -q tests/test_check_agent_os_approval_bundle_signature.py
```
