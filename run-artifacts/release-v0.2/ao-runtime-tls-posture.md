# AO Runtime TLS Posture

Date: 2026-05-11
Operator: Ubuntu Codex
Status: PASS - AO Runtime now has an executable TLS/mTLS, WAL HTTP HTTPS,
plain-WAL loopback, and advertised-primary discovery posture for the Factory
v0.2 cross-host worker path.

## Scope

Record the AO Runtime security-thread completion that followed the v0.2 live
worker validation. This status file tracks the `ao-runtime` commits that make
the cross-host transport posture explicit and testable from Factory v3 docs.

## AO Runtime Baseline

`ao-runtime` `origin/main` was verified at `383bb569`.

| Commit | Result |
| --- | --- |
| `94062a0` | `ao-worker` rejects non-loopback write-capable RuntimeService binds unless TLS is configured or the authenticated reverse-tunnel marker is set. |
| `8bfbb1a` | `ao-worker` loads RuntimeService server TLS/mTLS from `AO_WORKER_RUNTIME_TLS_CERT`, `AO_WORKER_RUNTIME_TLS_KEY`, and optional `AO_WORKER_RUNTIME_MTLS_CA`. |
| `282d48e` | `ao-worker` loads worker-to-coordinator client TLS/mTLS from `AO_COORDINATOR_TLS_CA`, optional client cert/key, and optional domain override. |
| `8a28dc4` | Daemon-owned coordinators load `[coordinator.tls]` from `AO_HOME/config.toml`, including direct paths or env-var-resolved paths. |
| `b5c839d0` | Ubuntu validation generates real PEM files, starts the daemon coordinator with mTLS, and registers `ao-worker` over `https://`. |
| `e5a2b0dd` | WAL HTTP is guarded to loopback: publishers reject non-loopback binds, followers reject non-loopback plain-HTTP WAL endpoints, and network WAL replication must use `https://` or a tunnel. |
| `15afe91f` | WAL advertised-primary discovery is implemented: `ao daemon replica join --from` accepts local paths, `file://`, loopback `http://`, and pinned non-loopback `https://` documents; non-loopback `http://` advertised-primary URLs are rejected and non-loopback `https://` requires `--expected-sha256`. |
| `d9eb68a` | WAL advertised-primary wrap-up coverage adds loopback HTTP fetch success and oversized advertised-primary rejection before replica config mutation; WAL design docs now record advertised-primary as implemented. |
| `0cdcdd2` | AO Runtime maturity roadmap records WAL advertised-primary as wrapped up and keeps native host validation as the next work. |
| `0c5850b` | Native deploy artifact validation is hardened with structured Mac launchd plist and Windows Task Scheduler XML parsing in the aggregate P6I deployment gate. |
| `c47d7e4` | Native Mac launchd installed-worker validation is recorded; native Mac launchd installed-worker validation covered Mac `plutil`, native `ao-worker` build, `launchctl bootstrap`, loaded-service inspection, and cleanup evidence; Windows native Task Scheduler validation remains blocked from Ubuntu by SSH authentication/MDM. |
| `383bb56` | WAL HTTP server TLS is implemented: `[coordinator.wal_http.tls]` serves `GET /replication/wal` over HTTPS with bearer auth, allows non-loopback WAL binds only when TLS is configured, keeps plain WAL HTTP loopback-only, and emits `https://.../replication/wal` in join-info when active. |

## Operator Contract

- Loopback plus authenticated SSH tunnels remains valid for Mac/Windows lanes.
- Plain LAN exposure of write-capable RuntimeService endpoints is forbidden.
- Non-loopback worker RuntimeService binds require either configured server TLS
  or `AO_WORKER_RUNTIME_NON_LOOPBACK_AUTH=authenticated-reverse-tunnel`.
- Coordinator TLS uses `[coordinator.tls]` in `AO_HOME/config.toml`.
- Worker coordinator client TLS uses `AO_COORDINATOR_TLS_*` environment
  variables.
- WAL HTTP publisher TLS uses `[coordinator.wal_http.tls]` in
  `AO_HOME/config.toml` with `cert`/`key` or env-var-name fields such as
  `AO_WAL_HTTP_TLS_CERT` and `AO_WAL_HTTP_TLS_KEY`.
- Plain WAL HTTP remains loopback-only: publishers without TLS must bind to
  loopback, and followers may consume only loopback `http://` WAL endpoints.
- Direct-network WAL replication uses `https://.../replication/wal` plus the
  configured bearer token environment variable; token values and private-key
  contents must not be stored in config, join-info, status, logs, or docs.
- WAL advertised-primary documents use schema
  `ao-runtime/advertised-primary/v1`. They may be consumed from local files,
  `file://`, loopback `http://`, or pinned non-loopback `https://` with
  `--expected-sha256`; they store endpoint URLs and environment variable names,
  not secret values.

## Verification

AO Runtime verification recorded through `383bb569`:

```bash
bash scripts/remote_transfer_v2_tls_ubuntu_validate.sh
bash scripts/remote_transfer_v2_transport_auth_validate.sh
bash scripts/remote_transfer_v2_p6i_deploy_validate.sh
cargo test -p ao-node wal_http_publisher_rejects_non_loopback_bind
cargo test -p ao-daemon wal_http
cargo test -p ao-cli ao_daemon_replica_add_rejects_plain_http_network_endpoint
cargo test -p ao-cli replica_join  # 6 advertised-primary tests
cargo test -p ao-node wal_http
cargo test -p ao-daemon primary_wal_http
cargo test -p ao-cli wal_http_join_info_uses_https_when_tls_configured
cargo test -p ao-cli
cargo test -p ao-daemon
cargo build --workspace --all-targets
cargo test --workspace
cargo fmt --all -- --check
python3 [REDACTED_LOCAL_PATH] --repo . --with-pytest --json
git diff --check
cargo clippy --workspace --all-targets -- -D warnings
bash evals/run_evals.sh
bash scripts/release_preflight.sh
rg -n "advertised-primary|expected-sha256|coordinator.wal_http.tls|Plain WAL HTTP remains loopback-only" docs deploy specs progress
```

Factory v3 documentation verification for this status update:

```bash
python3 scripts/check_cross_host_tls_posture.py --json
pytest -q tests/test_cross_host_tls_posture.py tests/test_cross_host_setup_doc.py tests/test_cross_host_tunnel_scripts.py tests/test_prepare_windows_outbound_bootstrap.py tests/test_windows_live_validation_progress.py
python3 scripts/validate.py
python3 [REDACTED_LOCAL_PATH] --repo . --with-pytest --json
git diff --check
```

## Remaining Work

- Mac and Windows installed worker lanes are statically validated in Factory v3
  with `scripts/check_cross_host_tls_posture.py`. The Mac launchd path now also
  has native AO Runtime evidence in
  `progress/slice-reports/native_installed_worker_validation.md`; re-run live
  host execution after any operator changes to tunnel ports, bind addresses, or
  TLS material.
- Advertised-primary discovery is committed for explicit WAL replica joins.
  Loopback HTTP fetch success and oversized document rejection are covered.
  Dynamic registry-backed WAL peer discovery remains future work until the
  advertised-primary path is exercised in the installed-worker lanes.
- WAL HTTP server TLS is complete for direct-network WAL replication. The next
  native validation gap is Windows Task Scheduler installed-worker validation
  from the Windows host.
