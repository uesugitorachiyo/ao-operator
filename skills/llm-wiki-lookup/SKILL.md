---
name: llm-wiki-lookup
description: "Manual read-only lookup against an external llm-wiki checkout when explicitly requested. Never part of default AO Operator planning, contracting, dispatch, or skill-promotion loops."
---

# LLM Wiki Lookup

Use this skill only when the user explicitly asks to consult `llm-wiki` or when
a task is specifically about maintaining the standalone `llm-wiki` repository.
AO Operator work must not depend on this skill for intake, contracting,
dispatch, or closure.

## Workflow

1. Confirm an external `llm-wiki` checkout is present before using it.
2. Search or query the `wiki` qmd collection for the narrow user-requested
   topic.
3. Read only the returned pages needed for the current task.
4. Treat results as background notes. Do not make AO Operator specs, plans,
   tests, or dispatch gates depend on them.
5. Do not create or update factory skills, `AGENTS.md`, or `CLAUDE.md` as a
   consequence of wiki lookup.

## Load Only If Needed

- `references/boundary.md` - private-wiki boundaries and forbidden uses.
- `references/lookup-flow.md` - qmd search/query/index commands and influence
  note format.
- `references/query-patterns.md` - focused searches for Spec Forge, workflow,
  and skill work.

## Exit Criteria

The task uses the wiki as read-only background only, avoids copying pages into
factory artifacts, and leaves factory skills and root instruction files
unchanged unless the user separately asks for those edits.
