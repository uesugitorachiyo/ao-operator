# AO Operator Public Release Runbook

This runbook keeps the public AO Operator repository generated from the
provenance repository. Do not hand-copy individual files unless this verifier
has already passed and the diff is intentionally scoped.

## Policy

- Source of truth: this repository.
- Public target: `../ao-public-repos/ao-operator`.
- Export tool: `scripts/public_clean_export.py`.
- Verification tool: `scripts/verify_public_clean_export.py`.
- Public artifact root: `run-artifacts/`.
- Provenance artifact root: `run-artifacts/`.
- Public export must not contain local machine paths, provider API keys, lab
  network targets outside approved scanner fixtures, raw transcripts, or
  unreleased Hermes/AO2 bridge internals.

## Verify Before Publishing

Run the full generated-export gate:

```sh
python scripts/verify_public_clean_export.py
```

The verifier exports to a temporary checkout, initializes git so workspace
tests behave like a real clone, then runs:

```sh
python scripts/check_public_release_security.py --json
python scripts/check_evidence_pack_replay_proof_status.py
python scripts/check_cross_host_tls_posture.py --json
python -m pytest -q
```

Expected result:

```text
verdict=PASS
```

## Publish

After the verifier passes, publish through the guarded helper:

```sh
python scripts/publish_public_clean_export.py --push
```

The helper verifies a temporary export, syncs into the public git checkout
without touching `.git`, re-runs the public gates in the real checkout, commits
only when the public tree changed, and pushes only when `--push` is present.

If any verification fails, fix the exporter or source artifact in this
repository first, then regenerate the public tree.
