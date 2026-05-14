# AO Prompt Samples

These prompts are production role templates for AO `kind: agent` tasks. The
full factory runner materializes task-specific prompts under
`run-artifacts/<slug>/prompts/` and injects upstream artifact contents, paths,
scoped reads/writes, provider selection, and contract context.

Every role should return:

```text
Result: DONE | DONE_WITH_CONCERNS | BLOCKED | REJECTED
Artifact: <path or event reference>
Evidence:
- <verification evidence>
Concerns:
- none | <concern>
Blocker: none | <required input>
```

Common boundaries:

- Use injected artifacts as authoritative scoped context.
- Do not include full transcripts.
- Do not include secret values.
- Do not dump environment variables.
- Do not invoke nested Codex, Claude, AO, or agent processes.
- Edit only declared scoped writes.
- If blocked, return `BLOCKED`; any blocker artifact must live inside a
  declared scoped write path.
