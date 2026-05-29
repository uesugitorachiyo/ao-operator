---
description: Render all pre-AO AO Operator artifacts for a brief without launching the team.
argument-hint: <brief-path-or-text> [slug]
---

# /ao-render — render artifacts only

Render the factory artifacts (RunSpec, role prompts, topology, contract) for the
task in `$ARGUMENTS` **without** launching any agent.

Steps:

1. Resolve a `--brief` (file path) and a kebab-case `--slug` from `$ARGUMENTS`.
2. From the ao-operator repo root, run:

   ```
   python3 scripts/factory_run.py --brief <BRIEF> --slug <SLUG> --render-only
   ```

3. List every generated artifact path and summarize the rendered RunSpec, role
   provider mapping, and verification gates.

Use this to inspect what the factory *would* run before committing to `/ao-run`.
