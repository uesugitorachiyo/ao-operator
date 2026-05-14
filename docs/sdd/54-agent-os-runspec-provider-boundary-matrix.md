# Agent OS RunSpec Provider Boundary Matrix

## Classification

- Size: MODERATE
- Shape: refactor
- Live provider: false
- Dispatch authorized: false

## Goal

Prove Agent OS RunSpec provider assignments stay explicit, profile-bound, and
consistent between the renderer report and rendered YAML. The matrix covers
Codex-only, Claude-only, mixed-provider, rendered YAML, and
provider-substitution refusal cases without running AO or provider CLIs.

## Matrix Cases

- Codex-only profile renders only `provider=codex`.
- Claude-only profile renders only `provider=claude`.
- Mixed-throughput profile renders both `claude` and `codex` according to the
  declared role provider map.
- Rendered YAML provider values match the renderer report provider values.
- Provider substitution is refused when a task provider differs from the
  profile-declared role provider.

## Negative Constraints

- Do not run AO.
- Do not run provider CLIs.
- Do not authorize dispatch.
- Do not accept rendered YAML that drifts from the renderer report.
- Do not silently substitute Codex for Claude or Claude for Codex.
- Do not accept unknown providers.

## Verification

```bash
python3 scripts/check_agent_os_runspec_provider_boundary_matrix.py --write-output --json
python3 -m pytest -q tests/test_agent_os_runspec_provider_boundary_matrix.py
python3 scripts/validate_factory.py --json
```
