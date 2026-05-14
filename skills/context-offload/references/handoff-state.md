# Handoff State

Create a durable handoff when:

- the session has accumulated many tool outputs,
- work is moving from research to implementation,
- the task spans multiple repos,
- context feels polluted, contradictory, or too large to audit,
- a later session must resume without re-reading everything.

Use this summary format:

```text
Goal:
Current state:
Decisions locked:
Files changed:
Commands run:
Open risks:
Next exact step:
```

Durable state belongs in repo artifacts: specs, plans, status logs,
evaluations, decisions, contracts, or README notes. Keep handoff summaries
factual and avoid embedding large source excerpts or command logs.
