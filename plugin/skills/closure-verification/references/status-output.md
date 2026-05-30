# Status Output

## STATUS Block

When returning to the factory, include:

```text
Result: DONE | DONE_WITH_CONCERNS | BLOCKED
Artifact: <paths>
Evidence: <commands and key outputs>
Concerns: <residual risks or none>
Blocker: <blocker or none>
```

## Final Response

Be explicit about tests that were not run. Do not hide failures behind vague
phrases like "should work." If a check is blocked by environment, name the
missing dependency or service.

Keep final responses concise but evidence-backed: what changed, where, what
passed, and what risk remains.
