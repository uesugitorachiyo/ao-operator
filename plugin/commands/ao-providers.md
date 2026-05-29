---
description: Print the resolved AO Operator role-to-provider routing.
argument-hint: [--provider-env <path>] [--profile <name>]
---

# /ao-providers — show provider routing

Show which provider (Claude, Codex, …) each AO role resolves to.

From the ao-operator repo root, run:

```
python3 scripts/factory_run.py --show-providers $ARGUMENTS
```

Report the role → provider table exactly as emitted. If `$ARGUMENTS` includes a
`--provider-env` or `--profile`, pass it through so the mapping reflects that
configuration.
