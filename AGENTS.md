# AO Operator — Agent Instructions

> GitHub repo slug: `ao-operator`. Legacy compatibility slug: `ao-operator`.
> Formerly "AO Operator" / "Plain Factory".

AO Operator uses ai-teams discipline with AO Runtime orchestration.

## Source Of Truth

- Architecture: `ao-operator.md`
- Setup: `SETUP.md`
- Prompt examples: `PROMPT_SAMPLES.md`
- RunSpecs: `ao/runspecs/`
- Role contracts: `agents/`

## Operating Rules

- Classify every task by size and shape before execution.
- Shape is one of `greenfield`, `bug-fix`, or `refactor`.
- Use scoped context only. Do not pass full conversation dumps to worker roles.
- Treat AO artifacts as the handoff boundary between roles.
- Every role returns evidence, concerns, and blocker state.
- Nothing is complete until evaluator-closer accepts the evidence.

## Hermes Integration Boundary

The intended Hermes architecture is permanent:

- Hermes is the front end, queue, cron trigger, and memory bookkeeping surface.
- AO Operator / AO Operator owns contracts, profiles, role discipline, evaluator
  closure, and governed workflow execution.
- AO2 owns trusted execution, memory, replay, and signed evidence boundaries.
- AO2 Control Plane is a read-only observer for signed evidence and memory
  exports; it must not sit in the trust path.

Hermes scheduled jobs must submit or invoke governed Factory/AO2 workflows
instead of using Hermes as a direct, arbitrary repo-mutating backend. If a task
cannot be routed through the governed Factory/AO2 path while preserving signed
evidence and evaluator closure, stop and report the boundary issue.

## Provider Rules

Each role resolves its provider from `.env`.

Valid values:

```text
claude
codex
```

Provider authentication must be local OAuth CLI only:

- `codex`: Codex CLI OAuth/subscription auth.
- `claude`: Claude Code CLI OAuth login.

`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and provider API-key auth paths are
forbidden. `scripts/factory_doctor.py` must fail when those variables are
present.
