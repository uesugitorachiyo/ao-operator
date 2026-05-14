# 40 - Manual Penetration Test Gate

Classification: COMPLEX
Shape: greenfield

## Scope

This slice records the manual penetration testing gate for AO Operator public
release readiness. It does not run live remote tests. It defines what must be
approved, tested, recorded, and cleaned up before any live adversarial network
exercise.

## Approval Boundary

Manual penetration testing requires explicit operator approval outside default
readiness checks. `FACTORY_V3_PENTEST_APPROVED=1` is the approval marker for a
future live lane, but this slice must always report
`manual_pentest_authorized=false`, `dispatch_authorized=false`, and
`live_providers_run=false`.

## Manual Scope

- Remote worker transfer staging, extraction, cleanup, and artifact return.
- Malformed bundle tests, including traversal attempt payloads, symlink entries,
  hardlink entries, device/special-file entries, excessive entry counts, and
  oversized archive bodies.
- Host-key mismatch behavior, unknown-host behavior, SSH known_hosts setup, and
  refusal of opportunistic trust.
- Provider credential boundary checks for OAuth files, provider CLI session
  state, API key variables, and token-shaped output.
- Operator approval bypass attempts for live provider dispatch, remote DAST,
  and manual pen-test execution.
- Generated artifact leak review and redaction for AO events, role artifacts,
  status reports, public release docs, and strict-public evidence.
- Denial-of-service rehearsal for prompt/status fanout, large returned
  artifacts, and repeated interrupted cleanup.

## Evidence Requirements

Every manual pen test report must include:

- report identifier and operator approval reference
- commands and exact target labels
- timestamps and duration
- host-key evidence and target cleanup evidence
- findings with severity, reproduction, and remediation status
- residual risk and explicit closure decision

## Stop Rules

- Stop if host identity is not pinned.
- Stop if the test requires provider API keys or copying OAuth files.
- Stop if cleanup cannot be confirmed.
- Stop if generated evidence contains token-shaped values, private keys,
  private network targets, or unredacted personal paths.
- Stop if operator approval is missing or ambiguous.

## Verification

```bash
python3 scripts/check_pentest_gate.py --write-output --json
```

## Acceptance Criteria

- Manual pen test scope is documented.
- Operator approval bypass testing is explicitly in scope.
- Live manual testing remains blocked by default.
- `manual_pentest_authorized=false`.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
