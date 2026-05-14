# Prompt Contracts

Use narrow prompts that make the return shape explicit.

## Read-Only Research

```text
Task:
Scope:
Read only these paths:
Do not edit:
Return only:
- files_read:
- findings:
- risks:
- recommendation:
- verification:
```

## Coding Subtask

```text
Task:
Shape:
Scope:
Own only:
Do not edit:
Verification:

You are not alone in the codebase. Do not revert others' edits. List changed
paths in your final answer.
```

## Reviewer Or Verifier

```text
Task:
Claims to verify:
Artifacts to inspect:
Commands allowed:
Return only:
- verdict:
- evidence:
- risks:
- missing checks:
```

Never dispatch full conversation dumps. Pass paths, current artifact names,
expected outputs, and the smallest useful acceptance criteria.
