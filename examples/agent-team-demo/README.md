# Agent Team Demo

This is the shortest public demo for the new AO Operator positioning:

```text
brief -> profile -> role graph -> RunSpec -> status artifacts
```

It is intentionally provider-free by default. The first goal is to show why AO
Operator is useful before spending subscription time on live Codex or Claude
Code runs.

## Try It

From the repository root:

```bash
bash scripts/first_run_demo.sh
```

Or run the commands manually:

```bash
python3 scripts/factory_run.py specify examples/agent-team-demo/task-brief.md \
  --slug agent-team-demo \
  --profile bug-fix \
  --overwrite-artifacts

python3 scripts/factory_run.py tasks agent-team-demo --profile bug-fix --json
```

Expected shape:

```text
intake -> planner -> implementer -> reviewer -> evaluator-closer
```

Expected artifacts:

```text
run-artifacts/agent-team-demo/
docs/specs/agent-team-demo-spec.md
docs/plans/agent-team-demo-plan.md
```

The evaluator artifact is produced by live closure flows, not the provider-free
dry run.

## Live Variant

After you inspect the dry run, use local provider CLI auth for a live run:

```bash
python3 scripts/factory_run.py \
  --brief examples/agent-team-demo/task-brief.md \
  --profile bug-fix \
  --slug agent-team-demo-live \
  --run
```

Do not set provider API keys. AO Operator is designed for local subscription
CLI auth.
