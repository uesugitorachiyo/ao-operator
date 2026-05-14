# Factory Closure

Use this for AO Operator, `claude-agent-teams-v2`, and
`codex-agent-teams-v2`.

## Preferred Gate

```bash
python3 scripts/verify_closure.py --repo . --with-pytest --json
```

The gate selects available repo-local checks, including factory doctor,
self-check, ledger check, and pytest.

## Debugging Failed Closure

Run narrower commands first when debugging:

```bash
python3 scripts/factory_doctor.py --json
python3 scripts/self_check.py --fast --json
python3 scripts/build_ledger.py --check --quiet
python3 -m pytest -q
```

If `build_ledger.py --check` fails because the ledger is stale, regenerate it
with `python3 scripts/build_ledger.py`, inspect the diff, then rerun closure.

## Broader Checks

Run broader checks before final closure when changes affect shared scripts,
agents, docs, dashboard, workflow, dispatch, or runtime boundaries.
