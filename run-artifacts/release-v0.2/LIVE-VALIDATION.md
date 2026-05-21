# v0.2 Live Validation

Date: 2026-05-10
Operator: Ubuntu Codex
Status: PASS - Factory remote submission now dispatches through the AO coordinator across Ubuntu, Mac, and Windows workers.

Post-validation transport hardening is now recorded in
`docs/status/release-v0.2/ao-runtime-tls-posture.md`. `ao-runtime` `origin/main`
through `383bb569` adds the non-loopback RuntimeService guard, worker
RuntimeService TLS/mTLS env loading, worker-to-coordinator client TLS/mTLS env
loading, daemon-owned coordinator `[coordinator.tls]`, Ubuntu real-PEM
validation, WAL HTTP loopback enforcement, WAL advertised-primary discovery,
WAL HTTP server TLS for direct-network HTTPS publication, stronger static
Mac/Windows deploy-artifact validation, and native Mac launchd installed-worker
validation.

## Scope

Validate the v0.2 live worker paths without operator copy/paste:

- Ubuntu coordinator running from `/tmp/ao-v02-live-home`.
- Ubuntu worker registered as `ubuntu-live-worker` with tag `ubuntu`.
- Mac RuntimeService reachable through SSH reverse tunnel as `mac-live-worker`
  with tags `mac,live`.
- Windows RuntimeService reachable through the Windows-initiated outbound SSH
  tunnel as `windows-live-worker` with tag `win`.
- D7 cross-host fixture executed from Ubuntu with `--remote`.
- Evidence profile executed from Ubuntu with `--remote`.
- Windows-tagged AO dispatch executed on the Windows worker.
- Provider-backed Windows Codex dispatch executed through the Windows worker
  PATH fix.

## Implementation Fixed During Validation

- `factory_run.py --remote` now uses the AO coordinator when
  `FACTORY_V3_REMOTE_COORDINATOR_URL` is set.
- Host tags map to worker node ids through `FACTORY_V3_REMOTE_NODE_FOR_TAGS_*`
  with defaults for `ubuntu` and `mac,live`.
- Remote task artifacts are streamed back into Factory evidence paths and AO
  event markdown.
- `remote_codex_smoke_flow` accepts unique run/task ids and emits raw streamed
  events so repeated Factory task dispatches do not collide with terminal
  coordinator state.
- The claude-mem scrubber now skips `scripts/factory_run.py` to avoid
  corrupting its own sentinel regex.

## Live Results

| Gate | Result | Evidence |
| --- | --- | --- |
| Deprecated Codex config | PASS | `~/.codex/config.toml` uses `[features].hooks`. |
| Mac RuntimeService smoke | PASS | `/tmp/ao-register-mac-smoke.json` returned `uname -s: Darwin` and hostname `Torachiyos-Mac-mini.local`. |
| D7 live cross-host pytest | PASS | `AO_LIVE_CROSS_HOST=1 ... pytest tests/e2e/test_cross_host_dispatch_e2e.py -q` passed in 124.55s. |
| Evidence profile via `--remote` | PASS | `docs/evaluations/cross-host-evidence-live-evaluation.md` verdict is `ACCEPTED`; AO completed 6 tasks. |
| Windows outbound registration | PASS | `docs/status/release-v0.2/windows-outbound-bootstrap/windows-live-validation-progress.md` records the registered `windows-live-worker` path. |
| Windows W4 dispatch proof | PASS | `docs/status/release-v0.2/windows-outbound-bootstrap/windows-w4-dispatch-proof.md` records marker `WINDOWS_W4_DISPATCH_OK`. |
| Windows Codex provider dispatch | PASS | `docs/status/release-v0.2/windows-outbound-bootstrap/windows-codex-path-live-smoke.md` records marker `WINDOWS_CODEX_PATH_OK`. |
| AO Runtime TLS posture | PASS | `docs/status/release-v0.2/ao-runtime-tls-posture.md` records `ao-runtime` `383bb569`, Ubuntu real-PEM mTLS validation, WAL HTTP loopback enforcement, WAL HTTP server TLS, advertised-primary discovery, wrap-up coverage, maturity-roadmap closure, structured native deploy-artifact validation, and native Mac launchd validation. |

## Key Artifacts

- `docs/status/factoryv3-cross-host-d7-live/`
- `docs/evidence/factoryv3-cross-host-d7-live/evidence-report.md`
- `docs/evaluations/factoryv3-cross-host-d7-live-evaluation.md`
- `docs/status/cross-host-evidence-live/`
- `docs/evidence/cross-host-evidence-live/evidence-report.md`
- `docs/evaluations/cross-host-evidence-live-evaluation.md`
- `docs/status/release-v0.2/mac-runtime-smoke.json`
- `docs/status/release-v0.2/windows-outbound-bootstrap/windows-live-validation-progress.md`
- `docs/status/release-v0.2/windows-outbound-bootstrap/windows-w4-dispatch-proof.md`
- `docs/status/release-v0.2/windows-outbound-bootstrap/windows-codex-path-live-smoke.md`
- `docs/status/release-v0.2/windows-outbound-bootstrap/windows-live-validation.json`
- `docs/status/release-v0.2/ao-runtime-tls-posture.md`

## Notes

- D7 proves split dispatch: intake and report-writer on Ubuntu, live-provider
  on Mac. The event log records `live-provider: node=mac-live-worker
  tags=mac,live finalStatus=completed`.
- The evidence profile has no per-role `host_tag` declarations, so the remote
  bridge routed it to the default Ubuntu worker while still exercising
  coordinator-backed dispatch.
- `validate_factory.py --slug ...` still assumes the baseline seven-role DAG and
  reports missing baseline role artifacts for profile-based runs; the Factory
  evaluation artifacts remain accepted because profile role artifacts exist and
  AO completed.
- Windows W4 is closed under the MDM-constrained topology: Windows initiates
  outbound SSH to Ubuntu, and Ubuntu-to-Windows SSH remains outside the valid
  control path. The live validation artifacts are in
  `docs/status/release-v0.2/windows-outbound-bootstrap/`.
- The secure transport posture is now executable in AO Runtime. Loopback plus
  authenticated SSH tunnels remains valid for the Mac/Windows lanes; any
  non-loopback worker RuntimeService bind requires TLS or the explicit
  authenticated reverse-tunnel marker. WAL advertised-primary discovery is
  available for explicit replica joins through local files, `file://`, loopback
  `http://`, or pinned non-loopback `https://` with `--expected-sha256`. WAL
  HTTP server TLS is now available through `[coordinator.wal_http.tls]` for
  direct-network `https://.../replication/wal`; plain WAL HTTP remains
  loopback-only.
- Factory v3 now has a static guard for the committed Mac/Windows runbooks and
  bootstrap artifacts: `python3 scripts/check_cross_host_tls_posture.py --json`.
