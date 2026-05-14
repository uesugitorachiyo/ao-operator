# Intake Research Offload

When offloading intake research, pass paths and questions, not full bodies. Keep
the request bounded and avoid full-conversation dumps.

Require the subagent to return only:

```text
files_read:
key_findings:
risks:
recommended_shape:
recommended_slices:
verification:
open_questions:
```

Use the result to sharpen the intake artifact. Do not treat subagent research as
authorization to dispatch implementers before the intake is validated.
