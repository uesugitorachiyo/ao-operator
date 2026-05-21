# Factory v3 - Release Notes v0.5.0

**Tag:** `v0.5.0`
**Tag commit:** `31e5e229`
**Ship date:** 2026-05-10
**Combined verdict:** READY
**Hard blockers:** none
**Safety posture:** `dispatch_authorized=false`; no live provider dispatch; Agent OS execution remains blocked until explicit approval is valid.

## What Ships

v0.5.0 is a focused operator-hardening release after `v0.4.0`.
It closes the post-v0.4 trail of small but important fixes that make
Factory v3's next safe action, blocked execution state, and current
RunSpec identity verifiable from committed artifacts rather than chat
history.

- **Plan-hardener role:** the default profile now includes a dedicated
  plan-hardener skill, with provider wiring and lockfile registration.
- **Queue recovery hardening:** stale queue recovery is deterministic
  under repeated or contended recovery attempts.
- **Redacted RunSpec validation:** topology validation accepts redacted
  prompt paths while still rejecting provider-secret leakage.
- **Next escalation summary:** escalation guidance is derived from
  committed gate artifacts instead of narrative state.
- **Operator cockpit hash visibility:** cockpit output exposes both the
  locked RunSpec hash and the current RunSpec hash for blocked
  execution.
- **Blocked execution evidence:** default blocked execution reports now
  record `current_runspec_sha256` and keep `would_run_provider=false`
  without launching providers.
- **Parity hygiene:** Mac-to-Ubuntu approval artifact parity was
  refreshed after each main advancement that changed non-allowlisted
  paths.

## Closure Criteria

| # | Criterion | State | Evidence |
|---|-----------|-------|----------|
| HD1 | Safe next command is machine-checkable with dispatch disabled. | CLOSED | `python3 scripts/check_operator_safe_next_command.py --json` returned `safe_action=START_NEXT_GATED_SDD_LANE`, `ship_ready=true`, `dispatch_authorized=false`. |
| HD2 | Operator cockpit reports locked and current RunSpec hashes. | CLOSED | `python3 scripts/agent_os_operator_cockpit.py --json` returned matching `runspec_sha256` and `current_runspec_sha256`. |
| HD3 | Blocked execution report records current RunSpec hash without provider execution. | CLOSED | `python3 scripts/run_agent_os_runspec_execution.py --write-output --json` returned expected `BLOCKED`, `runspec_sha256 == current_runspec_sha256`, and `would_run_provider=false`. |
| HD4 | Mac-to-Ubuntu approval artifact parity matches current main. | CLOSED | Mac-side parity refresh and local `python3 scripts/check_mac_ubuntu_approval_artifact_parity.py --json` returned PASS. |
| HD5 | Release readiness remains safe. | CLOSED | `python3 scripts/check_release_readiness.py` returned `verdict=PASS`, `ship_ready=true`, `dispatch_authorized=false`. |

## Verification Footprint

Ubuntu lane at release closure:

| Step | Command | Result |
|------|---------|--------|
| Targeted release notes and closure tests | `pytest -q tests/test_release_v0_5_plan.py tests/test_release_v0_5_closure.py` | PASS |
| Full closure | `python3 scripts/verify_closure.py --repo . --with-pytest --json` | PASS, `1129 passed, 4 skipped` |
| Release readiness | `python3 scripts/check_release_readiness.py` | PASS |
| Safe next command | `python3 scripts/check_operator_safe_next_command.py --json` | PASS |
| Mac-to-Ubuntu parity | `python3 scripts/check_mac_ubuntu_approval_artifact_parity.py --json` | PASS |

## Safety Boundary

The release did not perform, authorize, or materialize:

- No live provider dispatch
- Agent OS execution
- a new execution approval artifact
- Windows-initiated worker dispatch expansion
- any increase beyond the accepted 50-slice live baseline

## Commit Summary

Key commits included in `v0.5.0` after `v0.4.0`:

- `02543cd9` - Add dedicated plan hardener skill
- `12935eed` - Register plan hardener skill
- `b87d89cb` - Harden stale queue recovery under contention
- `edd1beeb` - Accept redacted RunSpec prompt paths in validation
- `08b1b88b` - Summarize next escalation from committed gate artifacts
- `be668311` - Show current RunSpec hash in operator cockpit
- `07f792ce` - Record current RunSpec hash in blocked execution report
- `1ecc2723` - Refresh default execution report hash evidence
- `62b118ad` - Open v0.5 operator hardening scope
- `6c80acb3` - Record v0.5 closure evidence
- `31e5e229` - Refresh parity after v0.5 closure

## Next Safe Step

Start a separate gated SDD lane. Keep Agent OS execution blocked until
a later lane supplies and validates an explicit approval artifact.
