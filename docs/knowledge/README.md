# Knowledge Sources

AO Operator does not use llm-wiki as part of its default planning, contracting,
dispatch, validation, or skill-promotion loops.

## Policy

- Do not copy llm-wiki pages into AO Operator.
- Do not make tests, doctors, or dispatch gates depend on an external wiki.
- Do not update `skills/`, `AGENTS.md`, or `CLAUDE.md` as a side effect of wiki
  lookup.
- Use `skills/llm-wiki-lookup/SKILL.md` only when the user explicitly asks for
  manual lookup against an external checkout.
- Factory artifacts must stand on local repo evidence even when external
  knowledge was manually consulted.
