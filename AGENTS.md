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
