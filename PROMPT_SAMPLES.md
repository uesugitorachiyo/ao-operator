# AO Operator — Prompt Samples

> Internal repo slug: `ao-operator`. Formerly "AO Operator" / "Plain Factory".

## Greenfield Complex App

Build a greenfield project management app with teams, projects, tasks, comments,
and an audit log. Use AO Operator. Classify the task, produce a scoped plan,
split frontend/backend/quality work only where slices are independent, and
require evaluator closure before done.

## Bug Fix

Use AO Operator to fix the failing task search behavior. First produce a failing
reproducer on HEAD, rank the top suspects with evidence, then dispatch the
smallest fix slice. Completion requires red-to-green test evidence.

## Refactor

Use AO Operator to refactor the billing service without changing observable
behavior. Establish the pinning suite first, define expected-diff boundaries,
slice into individually revertible steps, and require the suite to stay green.

## Cross-Lane Operator Fanout

Use AO Operator to build a complex SaaS dashboard by running independent
frontend, backend, and quality work branches under one AO DAG. Keep shared
contracts explicit and fan in through integrator and evaluator-closer.

See `examples/outperform-ai-teams-fanout/` for a concrete version with five
parallel work branches, Spec Forge, Ralph Loop, factory-manager fan-out, and
mixed Codex/Claude provider selection.

## Mixed Provider

Use Codex for implementer roles and Claude Code for reviewer and evaluator
roles. Keep provider selection in `.env`, not in the prompt, and use OAuth CLI
auth only.

## Full Claude Provider

Use `examples/claude-full/provider.env` to select Claude Code for every AO
Runtime Operator role. Require AO events showing `agent.run.claude`, `agent.detected` with
`provider=claude`, role artifacts with non-blocked STATUS, and evaluator
closure before reporting completion.

## Minimal Smoke

Validate AO Operator without changing project files. Render the smoke RunSpec,
run scaffold validation, run the factory doctor, and report evidence.

## Full Local Run

Use `examples/complex-app-smoke/task-brief.md` as the brief and run
`scripts/factory_run.py --slug complex-app-smoke --run`. Require generated spec,
plan, materialized prompts, AO events, role artifacts, and an evaluator artifact
with `Verdict: ACCEPTED` before reporting completion.
