# Requirements Style

Write requirements as testable EARS/RFC-2119 statements.

Prefer this shape:

```json
{
  "id": "SHALL-001",
  "condition": "WHEN <event or state>",
  "actor": "<system or role>",
  "requirement": "SHALL <testable behavior>",
  "rationale": "<why it matters>"
}
```

Every `requirement` must contain `SHALL`, `MUST`, `SHOULD`, or `MAY`.

Avoid vague requirements such as "works well" or "handles errors" unless the
acceptance criteria make them mechanically testable.
