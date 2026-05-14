# 43 - Supply-Chain Audit Gate

Classification: MODERATE
Shape: greenfield

## Scope

This slice records dependency and supply-chain release posture. AO Operator
currently has no third-party dependency manifest in the repository root. If a
dependency manifest is introduced, release readiness must require lockfile
pinning and a documented dependency review.

## Controls

- Dependency review is required when dependency manifests exist.
- Lockfile pinning is required for dependency manifests before public release.
- Vulnerability advisory review is required before approving release.
- License review is required before approving release.
- The gate remains non-dispatching and does not run live providers.

## Verification

```bash
python3 scripts/check_supply_chain_gate.py --write-output --json
```

## Acceptance Criteria

- Repositories without dependency manifests pass with a documented no-dependency
  posture.
- Repositories with dependency manifests fail unless a lockfile and audit-plan
  documentation exist.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
