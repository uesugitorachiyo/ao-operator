# Layered OpenClaw AO Example

This AO Operator mirror points at the AO Runtime example:

```text
${FACTORY_V3_AO_RUNTIME_PATH}/example/ao-operator-layered-orchestration
```

Use it when the target is more ambitious than the Hermes queue sample:

```text
OpenClaw:  submit / schedule / observe
AO Operator: contract / gate / route / evaluate / report
AO Runtime: execute providers / enforce policy / emit events
```

## Why This Is The Recommended Architecture

Hermes queueing is useful for worker saturation, but it is not the right owner
for Spec Forge, Ralph Loop, shape gates, slice ownership, provider routing, or
evaluator closure. AO Operator keeps those semantics explicit while AO Runtime
keeps execution eventful and policy-gated. OpenClaw stays focused on the
external product surface: chat, cron, webhook intake, status, cancellation, and
delivery.

The default example profile remains mixed because it fits this workload:

- Claude for Spec Forge, Ralph Loop, plan hardening, review, and evaluator
  closure.
- Codex for factory-manager, implementation-heavy branches, and integration.

That is a profile, not a hard-coded rule. Every exact task remains selectable
as `codex` or `claude` through `.env`.

## Run The Static AO Example Check

```bash
cd ${FACTORY_V3_AO_RUNTIME_PATH}
bash scripts/factory_v3_layered_orchestration_check.sh
```

## Start The Bounded Queue Runner

```bash
cd ${FACTORY_V3_AO_RUNTIME_PATH}/example/ao-operator-layered-orchestration
./start.sh --hours 0.05 --workers 2 --dry-run
```

The run writes `runs/<TIMESTAMP>/final-performance-report.md` with done,
failed, remaining, wall-clock speedup, worker-time speedup, and completed items
per hour. Use `--live-ao` only when the local Codex and Claude CLIs are
authenticated through OAuth/subscription flows.

For overnight AO Runtime self-improvement:

```bash
cd ${FACTORY_V3_AO_RUNTIME_PATH}/example/ao-operator-layered-orchestration
./start.sh --hours 8 --workers 4 --profile self-improvement --live-ao
```

That profile materializes
`prompts/ao-runtime-self-improvement-overnight.md` into the run artifact
directory and generates an item-specific AO RunSpec for provider execution.

## Validate The Contract From AO Operator

```bash
cd ${FACTORY_V3_ROOT}
python3 scripts/validate_intake.py \
  ${FACTORY_V3_AO_RUNTIME_PATH}/example/ao-operator-layered-orchestration/TASK-CONTRACT.json \
  --json
```

## Provider Profile

`provider.env` shows the recommended mixed-throughput defaults and exact task
overrides for this layered example.
