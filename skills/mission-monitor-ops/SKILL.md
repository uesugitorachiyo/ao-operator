---
name: mission-monitor-ops
description: "Use when operating, debugging, documenting, or extending mission-monitor dashboards for AO Operator, claude-agent-teams-v2, or codex-agent-teams-v2. Covers localhost ports, health/state/stream/file endpoints, specs/status/evaluation visibility, CLI transcript mirroring, and dashboard verification."
---

# Mission Monitor Ops

Use this skill for dashboard startup, diagnostics, endpoint changes, Specs panel
behavior, CLI transcript mirroring, or mission-monitor docs/tests.

## Workflow

1. Identify the provider repo and expected localhost port before starting or
   debugging the monitor.
2. Keep the monitor read-only: it observes repo files and worker artifacts, but
   does not own lifecycle or mutate state.
3. Check `/api/health` and `/api/state` before deeper dashboard debugging.
4. Inspect specs, status, evaluations, and ledger artifacts when UI state looks
   wrong.
5. Run monitor tests and factory self-checks after endpoint, parsing, or UI
   state changes.

## Load Only If Needed

- `references/ports-startup.md` - provider ports, startup commands, and bind
  safety.
- `references/read-only-contract.md` - monitor ownership and mutation boundary.
- `references/http-endpoints.md` - health, state, diagnostics, stream, and file
  endpoint checks.
- `references/artifact-visibility.md` - Specs panel, status, evaluation, and
  ledger inputs.
- `references/verification.md` - unit tests, self-checks, and concurrent
  provider smoke checks.

## Exit Criteria

The relevant provider monitor is checked on the correct localhost port, state
exposes provider context when available, read-only behavior is preserved, and
endpoint or UI changes have deterministic test or smoke evidence.
