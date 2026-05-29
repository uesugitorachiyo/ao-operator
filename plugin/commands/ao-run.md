---
description: Render AO Operator artifacts and launch the AO role team on a brief.
argument-hint: <brief-path-or-text> [slug]
---

# /ao-run — launch the factory

Run the AO Operator factory end-to-end on the task described by `$ARGUMENTS`.

Steps:

1. Resolve the brief. If `$ARGUMENTS` is a path to a markdown file, use it as
   `--brief`. Otherwise write the intent to a temp brief file first.
2. Pick a stable `--slug` (kebab-case). Use the second argument if provided.
3. From the ao-operator repo root, run:

   ```
   python3 scripts/factory_run.py --brief <BRIEF> --slug <SLUG> --run
   ```

4. Report the resolved provider mapping, generated artifact paths, and the
   STATUS / evidence outcome. Surface any concerns or blockers verbatim.

Do not invent results — report exactly what `factory_run.py` emits. If a gate
fails, stop and report the failing gate rather than continuing.
