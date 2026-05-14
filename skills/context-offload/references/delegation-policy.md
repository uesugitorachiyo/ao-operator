# Delegation Policy

Offload by default when the task needs:

- reading many files or long documents,
- comparing multiple repos,
- security, performance, UX, docs, or MCP review in parallel,
- independent verification commands,
- exploratory research whose intermediate findings do not need to stay in the
  parent context.

Keep work local when:

- the immediate next action is blocked on the result,
- the task is small enough that subagent overhead costs more than it saves,
- the work is tightly coupled to files already being edited in the parent,
- a risky decision requires direct user judgment.

The parent should retain only:

- paths,
- 1-3 line findings,
- decisions,
- risks,
- commands run,
- final evidence.

Do not paste raw source bodies, huge diffs, full logs, or long transcripts into
the parent unless the user explicitly asks.
