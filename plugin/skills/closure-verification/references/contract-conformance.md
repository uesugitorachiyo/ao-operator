# Contract Conformance

If a contract or spec declares runtime claims, verify them directly. Do not rely
on prose agreement.

## Common Checks

- Provider default docs match runtime settings.
- OAuth path does not pass raw API keys.
- Download paths reject traversal.
- Dashboard port matches `v2_config.toml`.
- `Shape:` and `Classification:` appear in emitted specs.
- `/api/state` exposes required provider, port, and repo root fields.
- Concurrent monitor claims are checked with both processes running.

Use `rg` for phrase checks and exact files for runtime checks.

## Reporting

Name the command or file inspection used for each runtime claim. If a claim
cannot be verified in the current environment, call that out as a concern or
blocker.
