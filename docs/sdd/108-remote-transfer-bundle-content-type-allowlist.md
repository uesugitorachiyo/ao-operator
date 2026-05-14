# Remote Transfer Bundle Content Type Allowlist

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that the remote-transfer wire boundary is fail-closed against
content-type and content-encoding abuse: a `content_type` not on the
receiver's allowlist MUST be rejected and MUST NOT be silently
coerced to a privileged allowlisted type; payload bytes whose magic
header does not match the declared `content_type` MUST be rejected
rather than dispatched on the basis of the declared type alone; a
`content_encoding` not on the encoding allowlist MUST be rejected
and MUST NOT silently fall back to identity decoding; and parameters
attached to `content_type` (such as `charset`) MUST be on the
parameter allowlist and MUST NOT contain path-traversal payloads or
other untrusted bytes that could be concatenated into filesystem
paths.

## Contract

`scripts/check_remote_transfer_bundle_content_type_allowlist.py`
emits `ao-operator/remote-transfer-bundle-content-type-allowlist/v1`.

The gate runs five deterministic cases (one control PASS + four
mutations FAIL) against an in-process content-type validation state
machine with a fixed `content_type` allowlist
(`application/x-factory-bundle`), a fixed `content_encoding`
allowlist (`identity`, `gzip`), a fixed `charset` parameter
allowlist (`utf-8`, `us-ascii`), and a fixed payload-magic mapping
(`application/x-factory-bundle` → `FBND`). Each case persists a
per-case `content-type-transcript.json` to a temporary work
directory and records `observed_verdict` next to
`expected_case_verdicts`.

Cases:

- `clean_allowlisted_content_type_passes` — control: sender declares
  `content_type=application/x-factory-bundle` and
  `content_encoding=identity`; payload magic is `FBND`;
  `receiver_validate_content_type` produces no errors.
- `unknown_content_type_silently_coerced_rejected` — mutation:
  sender declares `content_type=application/x-experimental-foo`,
  not on the allowlist; the receiver silently coerces it to
  `application/x-factory-bundle`; the verifier records
  `silently_coerced_unknown_content_type`.
- `mismatched_extension_to_content_type_rejected` — mutation:
  sender declares `content_type=application/x-factory-bundle` but
  ships payload with magic `%PDF`; the receiver dispatches based on
  the declared type without sniffing; the verifier records
  `dispatched_with_payload_magic_mismatch`.
- `unknown_content_encoding_silently_decoded_rejected` — mutation:
  sender declares `content_encoding=experimental-zstd`, not on the
  allowlist; the receiver silently falls back to identity decoding;
  the verifier records `silently_fell_back_to_identity_encoding`.
- `content_type_charset_parameter_smuggled_rejected` — mutation:
  sender declares
  `content_type=application/x-factory-bundle;charset=../../etc/passwd`;
  the receiver concatenates the parameter into a filesystem path
  during routing; the verifier records both
  `unsafe_charset_parameter` and
  `path_traversal_in_charset_parameter`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not write inside the repo working tree.
- Do not introduce randomness — all cases are deterministic with
  fixed synthetic content-type, encoding, and charset literals.
- Do not derive content-type values from real production traffic.

## Verification

```bash
python3 -m pytest -q tests/test_check_remote_transfer_bundle_content_type_allowlist.py
python3 scripts/check_remote_transfer_bundle_content_type_allowlist.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/remote-transfer-bundle-content-type-allowlist.json
```
