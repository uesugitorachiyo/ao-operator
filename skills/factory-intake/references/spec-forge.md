# Spec Forge Intake

Use Spec Forge for non-trivial intake when:

- acceptance criteria can be expressed as SHALL statements,
- fan-out or slice safety matters,
- docs/runtime/provider defaults must stay consistent,
- sensitive-field or trigger-review coverage is important,
- the user wants artifacts that survive session handoff.

## Command Shape

Run these from the target factory repo:

```bash
python3 scripts/spec_forge.py slice-plan docs/contracts/<slug>.json --target <claude|codex> --repo . --json
python3 scripts/spec_forge.py lint docs/contracts/<slug>.json --target <claude|codex> --target-repo .
python3 scripts/spec_forge.py emit docs/contracts/<slug>.json --target <claude|codex> --repo . --write
python3 scripts/validate_intake.py docs/contracts/<slug>.json --json
```

For MODERATE or COMPLEX work, run `slice-plan` before finalizing the contract
when slices are absent, tiny, overlapping, or hand-wavy. Treat the result as a
proposal: merge safe slices into the contract, then lint and dispatch-gate the
final contract.

If the contract is not ready, do not emit. Patch the contract first.

## Dispatch Gate

Before dispatching from a Spec Forge contract, run the factory dispatch gate:

```bash
python3 scripts/dispatch_gate.py docs/contracts/<slug>.json --json
```

Proceed only when the gate returns `PASS`. Dispatch only from the scoped
envelopes it returns.
