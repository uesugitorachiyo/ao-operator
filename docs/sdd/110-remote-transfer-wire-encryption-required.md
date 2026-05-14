# Remote Transfer Wire Encryption Required

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that the remote-transfer receiver is fail-closed against
unencrypted or weakly-encrypted bundle traffic on the wire: a bundle
delivered over a cleartext socket MUST be rejected and MUST NOT be
silently accepted; a TLS handshake that negotiates a transport
version outside the allowlist (e.g. tls1.0/tls1.1/tls1.2) MUST be
rejected and MUST NOT be silently downgraded; a TLS handshake that
negotiates a NULL or otherwise denied cipher suite MUST be rejected
and MUST NOT be allowed to carry a bundle even when the transport
version is allowlisted; and a per-bundle `encrypted=true` header
that is stripped by a man-in-the-middle after handshake MUST cause
the receiver to reject the bundle and MUST NOT be silently accepted
on the strength of the prior handshake metadata alone.

## Contract

`scripts/check_remote_transfer_wire_encryption_required.py` emits
`ao-operator/remote-transfer-wire-encryption-required/v1`.

The gate runs five deterministic cases (one control PASS + four
mutations FAIL) against an in-process wire-encryption verifier with
a fixed transport-version allowlist (`{"tls1.3"}`), a fixed cipher-
suite allowlist (`{"TLS_AES_256_GCM_SHA384",
"TLS_CHACHA20_POLY1305_SHA256"}`), and a fixed cipher-suite denylist
(`{"TLS_NULL_WITH_NULL_NULL", "TLS_RSA_WITH_NULL_SHA",
"TLS_RSA_WITH_RC4_128_SHA", "NULL"}`). Each case persists a per-case
`wire-encryption-transcript.json` to a temporary work directory and
records `observed_verdict` next to `expected_case_verdicts`.

Cases:

- `clean_encrypted_bundle_accepted` — control: sender negotiates an
  allowlisted transport (`tls1.3`) and an allowlisted cipher suite,
  preserves the per-bundle `encrypted=true` header end-to-end, and
  the receiver accepts; `receiver_validate_wire_encryption` produces
  no errors.
- `cleartext_bundle_silently_accepted_rejected` — mutation: sender
  ships the bundle over a cleartext (`plaintext`) socket and the
  receiver silently accepts it; the verifier records
  `silently_accepted_cleartext_bundle`.
- `downgraded_tls_cipher_silently_accepted_rejected` — mutation:
  sender negotiates a downgraded TLS version outside the transport
  allowlist (`tls1.0`) and the receiver silently accepts; the
  verifier records `silently_accepted_downgraded_transport`.
- `weak_null_cipher_suite_negotiated_rejected` — mutation: sender
  forces a NULL cipher suite (`TLS_NULL_WITH_NULL_NULL`) even though
  the transport version is allowlisted; the receiver silently
  accepts; the verifier records
  `silently_accepted_weak_cipher_suite`.
- `encryption_header_stripped_after_handshake_rejected` — mutation:
  sender announces `encrypted=true` at handshake but a man-in-the-
  middle strips the per-bundle encrypted header before the bundle
  reaches the receiver; the verifier records
  `silently_accepted_bundle_encryption_header_stripped_post_handshake`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not write inside the repo working tree.
- Do not introduce randomness — all cases are deterministic with
  fixed synthetic transport names, cipher-suite identifiers, and
  bundle handshake metadata.
- Do not derive transport versions or cipher names from real
  production handshakes.

## Verification

```bash
python3 -m pytest -q tests/test_check_remote_transfer_wire_encryption_required.py
python3 scripts/check_remote_transfer_wire_encryption_required.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/remote-transfer-wire-encryption-required.json
```
