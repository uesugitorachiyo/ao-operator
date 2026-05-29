---
description: List available AO Operator profiles.
---

# /ao-profiles — list profiles

List the profiles the factory can run under (e.g. financial-services).

From the ao-operator repo root, run:

```
python3 scripts/factory_run.py --list-profiles
```

Report each profile name and, where shown, its purpose. A profile is then
selected with `--profile <name>` on `/ao-run` or `/ao-render`.
