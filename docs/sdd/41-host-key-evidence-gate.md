# 41 - Host-Key Evidence Gate

Classification: COMPLEX
Shape: greenfield

## Scope

This slice records the host-key evidence required before remote DAST or manual
penetration testing can target a remote worker. It does not contact the remote
worker and does not authorize dispatch.

## Required Evidence

- Host-key pinning requires reviewed `known_hosts` evidence.
- Operators must verify the target with `ssh-keygen -F` against the intended
  `known_hosts` file.
- `ssh-keyscan` output may be used only as raw collection input; the reviewed
  fingerprint must be recorded before approval.
- Remote transfer commands must use `StrictHostKeyChecking=yes` and
  `UserKnownHostsFile`.
- Do not use `accept-new` for remote DAST, manual pentest, or live remote
  worker transfer approval.

## Verification

```bash
python3 scripts/check_host_key_evidence.py --write-output --json
```

## Acceptance Criteria

- `remote_dast_authorized=false`.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
- Host-key evidence requirements are documented before any remote DAST approval.
