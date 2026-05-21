# AO Operator Operator Release Runbook

Status: operator release-train runbook
Applies to: `ao-operator v0.7.0-ga`

This document is the operator-facing release guide for the private AO product
train. It intentionally covers private installation, verification,
troubleshooting, security posture, and what the product does not claim.

## Release Train

AO Operator is released as one member of the private AO train:

```text
ao-runtime v0.2.0-ga
ao-operator v0.7.0-ga
ao-control-plane v0.1.0-ga
financial-services-profile v0.1.0-ga
secure-agent-profile v0.1.0-ga
```

The strategy repository records train status and compatibility evidence:

```text
../ao-strategy/status/ao-private-release-train-2026-05-12.md
../ao-strategy/status/private-production-release-readiness-2026-05-12.md
```

Do not treat floating `main` branches as an official release. Use signed target
tags and the release-train evidence pack.

## Private Install

Prerequisites:

- AO Runtime checkout or release package available locally.
- Python 3.11+.
- Provider CLI login completed locally:
  - Codex CLI with ChatGPT-managed auth.
  - Claude Code CLI with OAuth login.
- No provider API-key environment variables set.
- Optional `cryptography` package only when producing Ed25519 evidence packs.
- `zstd` CLI when materializing `.tar.zst` evidence packs.

Install from source:

```sh
git clone git@github.com:uesugitorachiyo/ao-operator.git
cd ao-operator
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

Set AO Runtime location:

```sh
export FACTORY_V3_AO_RUNTIME_PATH="$HOME/Documents/ao-runtime"
```

The internal `FACTORY_V3_*` names are compatibility wire identifiers. The
product name is AO Operator.

## Verification

Run the local scaffold and provider-auth checks:

```sh
python3 scripts/validate_scaffold.py
python3 scripts/factory_doctor.py
python3 scripts/validate_factory.py --slug ao-operator-v0-7-ga-tagged --profile evidence --skip-repo-checks --allow-untracked-artifacts --allow-missing-final-evaluation
```

Verify the signed GA tag:

```sh
git fetch --tags origin
git tag -v v0.7.0-ga
```

Verify the AO-backed GA evidence pack:

```sh
python3 scripts/factory_run.py replay \
  run-artifacts/ao-operator-v0-7-ga-tagged/evidence-packs/evidence-pack-r-ao-operator-v0-7-ga-tagged-1778685620993228000.tar.zst \
  --ed25519-public-key run-artifacts/ao-operator-v0-7-ga-tagged/evidence-packs/evidence-pack-r-ao-operator-v0-7-ga-tagged-1778685620993228000/signatures/pubkey \
  --write-report /tmp/ao-operator-ga-replay.json
```

Expected replay verdict:

```text
signature=PASS
merkle=PASS
artifact references=PASS
deterministic replay=PASS or SKIPPED by task contract
```

Cross-check the train gate in AO Control Plane when validating the full release:

```sh
cd ../ao-control-plane
.venv/bin/python -m ao_control_plane.cli train-gate \
  --output .ao-control/release-train/ga-2026-05-13 \
  --require-target-tags \
  --verify-tag-signatures \
  --ao-operator-run ../ao-operator/run-artifacts/ao-operator-v0-7-ga-tagged \
  --secure-agent-run ../secure-agent-profile/runs/guarded-code-change-ga-tagged-20260513-v1 \
  --financial-services-earnings-run ../financial-services-profile/runs/earnings-note-ga-tagged-20260513-v1 \
  --financial-services-kyc-run ../financial-services-profile/runs/kyc-triage-ga-tagged-20260513-v1
```

## Troubleshooting

Provider auth fails:

- Run `codex login status` for Codex.
- Run Claude Code once interactively for Claude roles.
- Remove `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and `CODEX_API_KEY` from the
  environment.
- Re-run `python3 scripts/factory_doctor.py`.

AO Runtime path fails:

- Confirm `FACTORY_V3_AO_RUNTIME_PATH` points to the runtime checkout or package.
- Build or stage AO Runtime first:

```sh
cd "$FACTORY_V3_AO_RUNTIME_PATH"
cargo build --release -p ao-cli --bin ao --bin ao-policy --bin ao-worker
```

Evidence pack replay fails:

- Check whether the pack was signed with HMAC or Ed25519.
- Use the matching verification key.
- Do not copy private signing keys between hosts.
- Re-run replay with `--write-report` and inspect the first failing section:
  signature, Merkle, manifest coverage, transcript path, artifact reference, or
  deterministic replay.

Windows lane fails:

- Use Windows host (LAN IP recorded in the operator's local notebook, not in the
  repo).
- Use the dedicated SSH key recorded for the Windows lane.
- Keep Git Bash available at `C:\Program Files\Git\bin\bash.exe`.
- Confirm `git pull --ff-only` works non-interactively before running package or
  profile proof tasks.

## Security Posture

AO Operator coordinates local provider CLIs. It does not broker provider API
keys.

Security boundaries:

- Provider auth is local OAuth/subscription CLI auth only.
- Provider API-key environment variables are forbidden.
- Role context is scoped; full conversation dumps are not passed to worker roles.
- AO artifacts are the handoff boundary between roles.
- Evidence packs are signed and replayable.
- Production evidence packs use `.tar.zst` plus Ed25519.
- HMAC signing is local/dev fallback only.
- Private signing keys, provider auth files, browser cookies, and token caches
  must never be committed or copied into evidence packs.

Related runtime security record:

```text
../ao-runtime/docs/SECURITY-REVIEW.md
../ao-strategy/status/security-hardening-pass-2026-05-13.md
```

## What This Does Not Claim

AO Operator private GA does not claim:

- autonomous code merge without human review;
- hosted SaaS control-plane readiness;
- SOC 2 Type II certification;
- FINRA, HIPAA, PCI, or SEC compliance certification;
- autonomous trading, KYC approval, or regulated decisioning;
- sandbox escape prevention against a compromised host;
- provider credential custody;
- replacement for endpoint security, SIEM, or secrets management;
- public launch readiness.

The release claim is narrower and stronger: AO Operator can run local Codex and
Claude Code role chains through AO Runtime, enforce policy gates, and emit
signed replayable evidence for review.

## Closure Checklist

- [ ] Release train status reviewed in `ao-strategy`.
- [ ] Signed target tags verified.
- [ ] AO Operator GA pack replays.
- [ ] Provider API-key environment variables absent.
- [ ] Runtime release package available on the host.
- [ ] Windows lane proof is current.
- [ ] Private signing keys remain host-local.
- [ ] No public launch assets published from this private train.
