# Spec Forge Closure

Use this for `spec-forge-v2` and for contracts emitted from Spec Forge.

## Core Checks

```bash
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 -m spec_forge lint <contract.json> --target <claude|codex> --target-repo <repo> --json
PYTHONPATH=src python3 -m spec_forge emit <contract.json> --target <claude|codex> --repo /tmp/spec-forge-smoke --write
```

## Evidence Expectations

Closure should state:

- contract path,
- target repo,
- lint result,
- emit result or reason emit was not applicable,
- tests run,
- any intentionally unverified claims.
