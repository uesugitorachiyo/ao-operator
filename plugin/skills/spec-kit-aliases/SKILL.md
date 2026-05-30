---
name: spec-kit-aliases
description: Use when an operator asks for Spec-Kit-style commands in Plain Factory; maps specify, plan, tasks, and analyze vocabulary onto factory_run.py without bypassing gates.
---

# Spec-Kit Aliases

Use this skill when an operator asks for Spec-Kit-style commands in Plain
Factory.

Plain Factory keeps its native `factory_run.py` workflow, but exposes four
aliases for users who already think in Spec-Kit vocabulary:

- `specify <brief>`: render the greenfield starter chain for the brief.
- `plan <slug>`: show the planner-only route for an existing slug.
- `tasks <slug>`: list role tasks for a profile.
- `analyze <slug>`: show the Gate B / Gate R analysis route for a slug.

Rules:

- Do not bypass Factory gates.
- Do not introduce a second workflow engine.
- Treat aliases as vocabulary adapters over `factory_run.py`, not as a new
  orchestration layer.
- Keep output machine-readable with `--json` when automation is involved.
