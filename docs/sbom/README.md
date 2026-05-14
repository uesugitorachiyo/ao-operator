# SBOM — AO Operator (AO = AI Orchestration Operation; internal slug `ao-operator`)

Software Bill of Materials for the Python orchestrator. The Rust executor
(AO Runtime) maintains a separate SBOM in its own repository.

## Runtime Posture

The default production path under `scripts/` is **stdlib-only**. Optional
production features are lazy and operator-enabled:

- `cryptography` for Ed25519 evidence-pack signing and verification.
- `zstd` CLI for `.tar.zst` evidence-pack archive compression and replay.

Practical consequences:

- No transitive vulnerability inheritance into customer installs.
- Supply-chain budget is scoped to test/dev tooling unless optional production
  evidence-pack features are enabled.
- Installation requires a Python ≥3.11 interpreter; `pip` is only needed
  when running the test suite or enabling Ed25519 signing.

## Files

- `python-deps.json` — machine-readable SBOM for direct + transitive dev
  dependencies, generated from `importlib.metadata` (stdlib — no
  `pip-licenses` dependency).
- `python-deps.md` — human-readable rendering of the same data.

## Regenerate

```bash
python3 scripts/sbom_python.py > docs/sbom/python-deps.json
```

If `requirements-dev.txt` changes, regenerate and commit both SBOM files
in the same commit as the dependency change. SBOM regen is required for
any release tag once the v0.7 readiness lane lands.

## JSON Schema

```text
{
  "sbom_version": "1.0",
  "project": "ao-runtime-operator",
  "internal_slug": "ao-operator",
  "language": "python",
  "runtime_dependencies": [],          # always empty — stdlib-only
  "runtime_dependencies_note": "...",
  "optional_production_dependencies": [
    {
      "name": "...",
      "kind": "python-package" | "system-binary",
      "required": false,
      "used_for": "...",
      "activation": "...",
      "supply_chain_note": "..."
    }
  ],
  "dev_dependencies": [
    {
      "name": "...",
      "version": "...",
      "license": "...",
      "classifier": "...",             # OSI classifier when present
      "summary": "...",
      "kind": "direct" | "transitive"
    }
  ],
  "generated_at": "ISO-8601 UTC",
  "generator": "importlib.metadata (stdlib)"
}
```

## Out Of Scope

- Rust SBOM — lives in the `ao-runtime` repo (`cargo cyclonedx`).
- Provider CLI binaries (Codex, Claude Code) — operator-supplied; tracked
  under the host-validation lane, not the SBOM lane.
- Container/OS image SBOMs — `ao-operator` ships no container.
