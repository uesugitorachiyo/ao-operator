# AO Runtime Artifact Pipeline Big Task

Shape: refactor

Classification: COMPLEX

Goal: harden ao-runtime artifact capture, retrieval, and operator visibility
across daemon, CLI, TUI, docs, and tests without changing provider OAuth
semantics.

Context:

- AO Operator is the orchestrator for this task.
- The AO binary executing AO Operator MUST come from a separate clean runner
  ao-runtime worktree.
- The workspace mutated by AO Operator MUST be a separate target ao-runtime
  worktree.
- Use the all-Codex provider profile for the first bottleneck test so provider
  diversity does not hide AO Operator scheduling/runtime bottlenecks.

Required behavior:

1. Daemon artifact store
   - Persist normalized task artifacts from agent task completion events.
   - Preserve artifact metadata needed for CLI/TUI retrieval: run id, task id,
     artifact kind, path/name, size when known, and creation time.
   - Never persist OAuth tokens, raw auth files, or full environment dumps.

2. CLI artifact retrieval
   - Add or harden commands that list artifacts for a run and retrieve a
     selected artifact.
   - Returned output must be deterministic and script-friendly.
   - Missing run/task/artifact references must fail with clear errors.

3. TUI artifact visibility
   - Surface artifact availability in the run/task view.
   - Keep existing keyboard/help behavior stable.
   - Avoid blocking the TUI on artifact IO.

4. Event schema and docs
   - Document new or changed artifact events.
   - Update quickstart/operator docs with the retrieval workflow.

5. Tests
   - Add daemon integration coverage for artifact persistence.
   - Add CLI tests for list/retrieve success and not-found cases.
   - Add TUI tests or snapshots for artifact visibility.
   - Keep existing ao-runtime tests green.

Scoped writes:

- crates/ao-daemon/src/adapter.rs
- crates/ao-daemon/src/engine.rs
- crates/ao-daemon/src/error.rs
- crates/ao-daemon/src/state.rs
- crates/ao-daemon/tests/agent_task.rs
- crates/ao-daemon/tests/event_store_engine_integration.rs
- crates/ao-cli/src/commands/run.rs
- crates/ao-cli/src/lib.rs
- crates/ao-cli/tests/cli_milestone.rs
- crates/ao-tui/src/bin/ao-tui.rs
- crates/ao-tui/src/model.rs
- crates/ao-tui/src/view.rs
- crates/ao-tui/tests/binary_snapshot.rs
- crates/ao-tui/tests/cli_help.rs
- docs/QUICKSTART.md
- docs/event-log-schema.md
- example/agent-team/ao-runspec/README.md
- specs/2026-05-05-ao-operator-artifact-pipeline.md
- progress/slice-reports/S27_factory_v3_artifact_pipeline.md

Pinning suite:

- cargo test -p ao-daemon
- cargo test -p ao-cli
- cargo test -p ao-tui
- cargo fmt --all -- --check
- cargo clippy --workspace --all-targets -- -D warnings

Acceptance:

- AO Operator generates spec, plan, status, prompts, RunSpec, role artifacts,
  and evaluation artifacts for this task.
- The run records clear timing and queue/drain evidence suitable for bottleneck
  analysis.
- The target ao-runtime worktree contains only scoped changes for this task.
- The clean runner ao-runtime worktree remains clean after execution.
- All pinning-suite commands above pass or the evaluator records a concrete
  blocker with evidence.

Negative constraints:

- Do not use `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.
- Do not read or emit OAuth token files.
- Do not run AO Operator using the same ao-runtime worktree being edited.
- Do not treat a dirty runner ao-runtime worktree as baseline evidence.
- Do not mix unrelated ao-runtime changes into the target branch.
