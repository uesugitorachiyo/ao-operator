# Stress Topology Development Recipe

AO Operator now has a large-topology stress lane in
`examples/remote-transfer-v2-stress/`. It is intentionally bigger than the
original 17-task `outperform-ai-teams-fanout` example: the checked-in stress
lane materializes 2007 tasks from a generated 1000-slice fixture.

The generator also supports two non-writing ceiling probes:

- 25000 slices / 50007 tasks: topology validator probe that exercises the
  AO Operator contract and DAG parser against a temporary topology file.
- 100000 slices / 200007 tasks: count-only ceiling probe that validates
  generator bounds and scale math without writing repository artifacts.

The checked-in fixture also includes bounded live profile support:

- `remote-transfer-v2-stress-live`: accepted at 25 slices / 57 tasks, using
  `examples/remote-transfer-v2-stress/ao-live-stress-topology.yaml` and
  `examples/remote-transfer-v2-stress/spec-forge.live.contract.json`.
- 50-slice / 107-task preparation uses a temporary worktree and commits only a
  compact dry-run report. It does not replace accepted 25-slice live evidence.
- Operator slices are declared in
  `examples/remote-transfer-v2-stress/operator-slices.json` and validated by
  `python3 scripts/validate_operator_slices.py`.

## Purpose

Use a large Remote Transfer v2 planning workload to stress AO Operator without
running live providers:

- 5 control-gate tasks: planner-intake, Spec Forge, Ralph Loop, plan-hardener,
  and factory-manager.
- 1000 implementation factory tasks.
- 1000 matching reviewer tasks.
- 2 fan-in closure tasks: integrator and evaluator-closer.

The 2007-task lane pushes prompt materialization, RunSpec generation, topology
parsing, contract validation, provider resolution, and exact prompt-set
validation without risking provider spend or network-side effects. The
50007-task validator probe pushes contract/topology validation only, which
avoids hundreds of megabytes of additional generated prompt artifacts. The
200007-task ceiling probe is deliberately count-only until the repository-size
and review-cost tradeoff for a larger topology parser run is explicit.

Live provider execution must start with the bounded live profile. Do not run the
1000-slice topology with `--run`; it is a dry-run materialization stress lane.
`factory_run.py --run` blocks topologies above `FACTORY_V3_MAX_LIVE_TASKS`
(default: 50) unless `FACTORY_V3_ALLOW_LARGE_LIVE_RUN=1` is set with
documented provider-limit evidence.

## Conduct Loop

1. Update the stress brief, contract, and topology together.
2. Run the dry-run materializer:

```bash
python3 scripts/factory_run.py \
  --brief examples/remote-transfer-v2-stress/task-brief.md \
  --slug remote-transfer-v2-stress \
  --provider-env examples/remote-transfer-v2-stress/provider.env \
  --topology examples/remote-transfer-v2-stress/ao-stress-topology.yaml \
  --dry-run \
  --overwrite-artifacts
```

3. Validate the generated artifact set:

```bash
python3 scripts/validate_factory.py \
  --slug remote-transfer-v2-stress \
  --topology examples/remote-transfer-v2-stress/ao-stress-topology.yaml \
  --contract examples/remote-transfer-v2-stress/spec-forge.contract.json \
  --json
```

4. Run the intake validator against the contract:

```bash
python3 scripts/validate_intake.py \
  examples/remote-transfer-v2-stress/spec-forge.contract.json \
  --json
```

5. For the topology-only validator probe, validate a temporary generated DAG
   without writing fixture files:

```bash
python3 scripts/generate_stress_fixture.py --slices 25000 --check-only --validate-topology
```

6. For the maximum count-only ceiling probe, validate scale math without writing
   fixture files:

```bash
python3 scripts/generate_stress_fixture.py --slices 100000 --check-only
```

7. Run normal closure without the heavy stress test in the default pytest path:

```bash
python3 scripts/verify_closure.py --with-pytest --json
```

8. Run the opt-in pytest stress case when changing generator ceilings or
   topology validator behavior:

```bash
FACTORY_V3_RUN_STRESS_TESTS=1 python3 -m pytest -q tests/test_validate_factory_topology.py
```

9. Validate the operator slice manifest:

```bash
python3 scripts/validate_operator_slices.py \
  examples/remote-transfer-v2-stress/operator-slices.json \
  --json
```

10. For live provider validation, start with the current bounded profile:

```bash
python3 scripts/factory_run.py \
  --brief examples/remote-transfer-v2-stress/task-brief-live.md \
  --slug remote-transfer-v2-stress-live \
  --provider-env examples/remote-transfer-v2-stress/provider.env \
  --topology examples/remote-transfer-v2-stress/ao-live-stress-topology.yaml \
  --run \
  --overwrite-artifacts \
  --scrub-root-context
```

Only increase the bounded live slice count after the current profile completes
without provider limit, auth, network, or closure blockers.

## Operator Slice Ladder

Use these slices in order. Each slice produces evidence for the next decision;
do not skip directly from dry-run materialization to a 1000-slice live run.

1. Preserve failed-run diagnostics before reruns:

```bash
mkdir -p run-artifacts/remote-transfer-v2-stress/failure-snapshots

cp -a /tmp/ao-operator-ao-remote-transfer-v2-stress \
  run-artifacts/remote-transfer-v2-stress/failure-snapshots/ao-home-$(date +%Y%m%d-%H%M%S)

python3 scripts/summarize_ao_failure.py \
  /tmp/ao-operator-ao-remote-transfer-v2-stress \
  --json
```

2. Keep the 1000-slice profile as dry-run materialization evidence only:

```bash
python3 scripts/factory_run.py \
  --brief examples/remote-transfer-v2-stress/task-brief.md \
  --slug remote-transfer-v2-stress \
  --provider-env examples/remote-transfer-v2-stress/provider.env \
  --topology examples/remote-transfer-v2-stress/ao-stress-topology.yaml \
  --dry-run \
  --overwrite-artifacts \
  --scrub-root-context
```

3. Run the bounded 10-slice live profile only after `factory_doctor.py` passes.

4. If the 10-slice live profile is accepted, regenerate a 25-slice live profile
   in a separate change and validate it before running:

```bash
python3 scripts/generate_stress_fixture.py --live-slices 25 --write-live-profile
python3 scripts/factory_run.py \
  --brief examples/remote-transfer-v2-stress/task-brief-live.md \
  --slug remote-transfer-v2-stress-live \
  --provider-env examples/remote-transfer-v2-stress/provider.env \
  --topology examples/remote-transfer-v2-stress/ao-live-stress-topology.yaml \
  --dry-run \
  --overwrite-artifacts \
  --scrub-root-context
python3 scripts/validate_intake.py \
  examples/remote-transfer-v2-stress/spec-forge.live.contract.json \
  --json
python3 scripts/validate_factory.py \
  --slug remote-transfer-v2-stress-live \
  --topology examples/remote-transfer-v2-stress/ao-live-stress-topology.yaml \
  --contract examples/remote-transfer-v2-stress/spec-forge.live.contract.json \
  --json
```

The dry-run materialization step is required because `validate_factory.py`
validates the topology against the generated RunSpec, prompt set, and role
artifact layout for the current slug. Regenerating only the topology and
contract leaves stale 10-slice artifacts behind.

5. Escalate above 50 live tasks only after the prior live profile has no
   provider-limit, auth, network, or closure blockers. The operator must set
   `FACTORY_V3_ALLOW_LARGE_LIVE_RUN=1`, capture the expected provider limit
   evidence in the status doc, and preserve AO diagnostics before any rerun.

6. Prepare the 50-slice profile without mutating accepted evidence:

```bash
python3 scripts/prepare_live_profile_dry_run.py \
  --slices 50 \
  --report run-artifacts/remote-transfer-v2-stress/profile-prep/50-slice-dry-run-prep.json
```

This command creates a temporary git worktree, generates the 50-slice live
profile there, dry-runs it there, validates intake and factory artifacts there,
and writes only the report into the main worktree. Commit the prep report and
operator-run receipt only. Do not commit the temporary 50-slice profile files as
accepted live evidence.

7. Check the 50-slice live approval gate before considering provider dispatch:

```bash
FACTORY_V3_ALLOW_LARGE_LIVE_RUN=1 \
python3 scripts/check_50_slice_live_approval_gate.py \
  --write-output \
  --json
```

The gate requires the committed 50-slice prep report and accepted 25-slice live
evidence. It is not dispatch authorization; the output must keep
`dispatch_authorized=false` until a separate 50-slice live approval exists.

8. Record the provider budget and no-provider rehearsal before adding approval:

```bash
FACTORY_V3_ALLOW_LARGE_LIVE_RUN=1 \
python3 scripts/check_50_slice_provider_budget.py \
  --write-output \
  --json

python3 scripts/rehearse_50_slice_live_sequence.py \
  --write-output \
  --json
```

The rehearsal must show that the live operator slice blocks without
`--allow-live` and that `scripts/run_50_slice_live.py` blocks without the
explicit approval JSON. It must keep `dispatch_authorized=false`.

9. After a real 50-slice live attempt, route the result through the
   50-slice-specific postrun router:

```bash
python3 scripts/route_50_slice_live_postrun.py \
  --write-output \
  --json
```

The router checks the current live contract slice count. Accepted 25-slice
evidence remains accepted 25-slice evidence; it is not accepted 50-slice
evidence.

10. Generate the operator summary before any approval decision:

```bash
python3 scripts/summarize_50_slice_operator_state.py \
  --write-output \
  --json
```

The summary is the operator-facing checkpoint. It names the current state,
blockers, approval status, next safe command, and evidence paths.

## Stop Rules

- Stop if provider resolution requires anything other than `codex` or `claude`.
- Stop if `--run` reports `FACTORY_V3_MAX_LIVE_TASKS`; switch to the bounded
  live profile instead of bypassing the guardrail.
- Stop if any factory slice lacks a matching reviewer.
- Stop if two factory slices declare overlapping write ownership without an
  explicit integrator-owned merge contract.
- Stop if generated prompts are missing scoped context, injected artifacts,
  relevant skills, or the required STATUS block.
- Stop if the topology cannot validate exactly against the generated prompt set.

## Workarounds

- If the goal is to increase task count beyond 2007, start with
  `--check-only` and topology validator tests. Do not materialize the full
  prompt corpus until the repository-size and review-cost tradeoff is explicit.
- If the goal is to exceed the 50007-task validator probe, first use the
  200007-task count-only ceiling probe and then raise the validator probe in a
  separate change with timing and memory evidence.
- If validation becomes too slow, regenerate a smaller fixture with
  `python3 scripts/generate_stress_fixture.py --slices <N>` and skip live run;
  this lane is primarily a dry-run materialization stress test.
- If default closure becomes slow, keep the 50007-task pytest case gated behind
  `FACTORY_V3_RUN_STRESS_TESTS=1` and use the generator CLI command as the
  durable stress evidence.
- If provider rate limits would make a live run unsafe, keep provider profile
  all-Codex and use `--dry-run`, or use the 10-slice bounded live profile
  instead of the 1000-slice topology.
- If one Remote Transfer v2 domain needs more detail, split the domain in the
  contract and add another factory/reviewer pair rather than expanding the
  prompt for an existing slice.
- If topology YAML becomes hard to review, keep task IDs deterministic and
  grouped as all factories first, then all reviewers, then fan-in. The
  generator preserves that ordering.
