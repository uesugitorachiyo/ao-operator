# SDD 80: Mac Ubuntu Approval Artifact Parity

## Goal

Prove Mac and Ubuntu agree on the committed approval evidence artifacts before
starting signed remote approval transfer work.

## Scope

- Compare a bounded approval evidence manifest by SHA-256 on Mac and Ubuntu.
- Exclude aggregate reports that are refreshed by this lane, such as the
  operator guardrail summary and release artifact index.
- Require matching Git heads for the compared repository state.
- Run only non-dispatching approval proof checks on Ubuntu.
- Record a committed parity report with redacted remote host and path details.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not copy private signing keys or provider credentials.
- Do not use opportunistic SSH trust.
- Do not include the parity report itself in its recursive artifact manifest.

## Verification

```bash
python3 scripts/check_mac_ubuntu_approval_artifact_parity.py --remote-host "$FACTORY_V3_REMOTE_HOST" --write-output --json
python3 scripts/check_mac_ubuntu_approval_artifact_parity.py --json
python3 -m pytest -q tests/test_check_mac_ubuntu_approval_artifact_parity.py
```
