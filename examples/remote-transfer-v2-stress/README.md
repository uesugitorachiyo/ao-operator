# Remote Transfer v2 Stress Topology

This fixture stress-tests AO Operator with a 2007-task Remote Transfer v2
factory-of-factories topology.

It is a dry-run/materialization lane by default. It does not run live providers,
does not transfer credentials, and does not expose network endpoints.

Current operator handoff:
`run-artifacts/remote-transfer-v2-stress/operator-handoff-20260506.md`

Bounded live acceptance runbook:
`run-artifacts/remote-transfer-v2-stress-live/live-acceptance-runbook-20260506.md`

## Commands

```bash
python3 scripts/factory_run.py \
  --brief examples/remote-transfer-v2-stress/task-brief.md \
  --slug remote-transfer-v2-stress \
  --provider-env examples/remote-transfer-v2-stress/provider.env \
  --topology examples/remote-transfer-v2-stress/ao-stress-topology.yaml \
  --dry-run \
  --overwrite-artifacts

python3 scripts/validate_factory.py \
  --slug remote-transfer-v2-stress \
  --topology examples/remote-transfer-v2-stress/ao-stress-topology.yaml \
  --contract examples/remote-transfer-v2-stress/spec-forge.contract.json \
  --json

python3 scripts/validate_intake.py \
  examples/remote-transfer-v2-stress/spec-forge.contract.json \
  --json

python3 scripts/generate_stress_fixture.py --slices 25000 --check-only --validate-topology

python3 scripts/generate_stress_fixture.py --slices 100000 --check-only

FACTORY_V3_RUN_STRESS_TESTS=1 python3 -m pytest -q tests/test_validate_factory_topology.py

python3 scripts/validate_operator_slices.py \
  examples/remote-transfer-v2-stress/operator-slices.json \
  --json

python3 scripts/validate_operator_slices.py \
  examples/remote-transfer-v2-stress/operator-slices.json \
  --list-slices \
  --local-only \
  --json

python3 scripts/run_operator_slice.py \
  examples/remote-transfer-v2-stress/operator-slices.json \
  --from 01-ao-runtime-doctor \
  --through 11-review-runtime-guardrail-batch \
  --local-only \
  --json

python3 scripts/run_operator_slice.py \
  examples/remote-transfer-v2-stress/operator-slices.json \
  --slice 02-validate-bounded-live-profile \
  --execute \
  --json

python3 scripts/check_bounded_live_readiness.py --json

python3 scripts/check_bounded_live_readiness.py --write-summary --json

python3 scripts/build_live_dispatch_packet.py --write-packet --json

python3 scripts/verify_live_dispatch_packet.py --json

python3 scripts/check_live_dispatch_gate.py --ao-runtime-path ${FACTORY_V3_AO_RUNTIME_PATH} --write-gate --json

python3 scripts/classify_live_outcome.py --write-output --json

python3 scripts/plan_live_failure_diagnostics.py --write-plan --json

python3 scripts/preserve_live_failure_diagnostics.py --write-report --json

python3 scripts/route_live_postrun.py --write-output --json

python3 scripts/check_live_success_commit_guard.py --write-output --json

python3 scripts/check_live_operator_sequence.py --write-output --json

python3 scripts/check_live_approval_readiness.py --write-output --json

python3 scripts/check_live_acceptance.py \
  --slug remote-transfer-v2-stress-live \
  --json

# Failure diagnostics after a blocked or provider-limited live attempt.
python3 scripts/summarize_ao_failure.py \
  /tmp/ao-operator-ao-remote-transfer-v2-stress \
  --json

# Bounded live provider profile. Start here for live AO runs.
python3 scripts/factory_run.py \
  --brief examples/remote-transfer-v2-stress/task-brief-live.md \
  --slug remote-transfer-v2-stress-live \
  --provider-env examples/remote-transfer-v2-stress/provider.env \
  --topology examples/remote-transfer-v2-stress/ao-live-stress-topology.yaml \
  --run \
  --overwrite-artifacts \
  --scrub-root-context
```

## Scale

- 2007 topology tasks.
- 1000 implementation factories.
- 1000 reviewer tasks.
- 1 integrator fan-in.
- 1 evaluator closure.
- 27-task bounded live profile available as `remote-transfer-v2-stress-live`.
- 34 ordered operator slices in `operator-slices.json`.
- 50007-task topology validator probe available with `--check-only --validate-topology`.
- 200007-task count-only ceiling probe available with `--check-only`.

## Safety

- OAuth CLI providers only.
- No provider API-key env vars.
- No live Mac-to-Ubuntu endpoint exposure.
- No provider credential transfer.
- No full transcript handoffs.
- Operator-run reports redact provider auth paths, token/API-key shaped values,
  and raw AO home paths before they are written.
- Do not run the 1000-slice topology with live providers; use the bounded live
  profile first.
- Live runs above `FACTORY_V3_MAX_LIVE_TASKS` (default: 50) are blocked unless
  `FACTORY_V3_ALLOW_LARGE_LIVE_RUN=1` is set with documented provider-limit
  evidence.
