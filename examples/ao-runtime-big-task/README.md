# AO Runtime Big-Task Harness

This harness is the first real AO Operator bottleneck test against ao-runtime.
It separates the runtime that executes AO Operator from the runtime worktree
AO Operator edits.

```bash
python3 scripts/prepare_ao_runtime_big_task.py
```

Default layout:

- Runner AO worktree: `/tmp/ao-operator-ao-runtime-runner`
- Target AO worktree: `/tmp/ao-operator-ao-runtime-target`
- Target branch: `ao-operator/ao-runtime-big-task-target`
- Provider profile copied into target:
  `/tmp/ao-operator-ao-runtime-target/.ao-operator/all-codex.env`
- Brief:
  `examples/ao-runtime-big-task/artifact-pipeline-brief.md`

Build the clean runner AO binary:

```bash
python3 scripts/prepare_ao_runtime_big_task.py --build-runner
```

Run the first non-provider validation:

```bash
FACTORY_V3_AO_BIN=/tmp/ao-operator-ao-runtime-runner/target/release/ao \
python3 scripts/factory_run.py \
  --brief examples/ao-runtime-big-task/artifact-pipeline-brief.md \
  --slug ao-runtime-artifact-pipeline-big-task \
  --provider-env /tmp/ao-operator-ao-runtime-target/.ao-operator/all-codex.env \
  --workspace /tmp/ao-operator-ao-runtime-target \
  --overwrite-artifacts \
  --scrub-root-context \
  --dry-run
```

The live run uses the same command with `--run` after the runner AO worktree is
built and clean.
