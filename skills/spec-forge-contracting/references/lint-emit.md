# Lint Emit And Conformance

## From `spec-forge-v2`

```bash
PYTHONPATH=src python3 -m spec_forge slice-plan <contract.json> --target <claude|codex> --repo <repo> --json
PYTHONPATH=src python3 -m spec_forge lint <contract.json> --target <claude|codex> --target-repo <repo> --json
PYTHONPATH=src python3 -m spec_forge emit <contract.json> --target <claude|codex> --repo <repo> --write
PYTHONPATH=src python3 -m pytest -q
```

## From A Factory Repo

```bash
python3 scripts/spec_forge.py slice-plan <contract.json> --target <claude|codex> --repo . --json
python3 scripts/spec_forge.py lint <contract.json> --target <claude|codex> --target-repo . --json
python3 scripts/spec_forge.py emit <contract.json> --target <claude|codex> --repo . --write
```

`slice-plan` proposes deterministic slices from acceptance-criteria file hints.
It does not mutate the contract and does not dispatch agents. Copy the accepted
proposal into `slices[]`, then run lint and dispatch gate.

## Post-Build Conformance

After implementation, verify declared claims against files. Examples:

- `rg` docs/runtime for provider defaults,
- assert generated files exist under expected paths,
- run the AC verification commands,
- check sensitive-field handling with focused tests or source reads.

If conformance requires manual review, record that in evaluation artifacts.
