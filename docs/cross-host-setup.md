# Cross-Host Worker Setup

This runbook brings Ubuntu, Mac, and Windows onto the v0.2 remote
orchestration path. Ubuntu hosts the AO coordinator. Mac and Windows connect
outbound through SSH tunnels and run `ao-worker` locally, so provider OAuth
credentials stay on their home host.

## Prerequisites

- AO Operator (AO = AI Orchestration Operation; repo: `ao-operator`) and
  `ao-runtime` are up to date on each host.
- Provider CLIs are logged in locally with OAuth/subscription auth only.
- No `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` is present.
- Ubuntu SSH is reachable from Mac and Windows.
- `ao-worker` is available on each worker host. Build it from source, or use an
  AO Runtime release artifact at `dist/<platform>/bin/ao-worker`:

```sh
cd /path/to/ao-runtime
cargo build --release -p ao-cli --bin ao-worker
# Or stage the release artifact that includes ao, ao-policy, and ao-worker:
bash scripts/release.sh
```

When installing from a staged AO Runtime release artifact, keep
`dist/<platform>/SHA256SUMS` and `dist/<platform>/RELEASE-MANIFEST.json` with
the package. The manifest records the expected binary paths, sizes, and
SHA-256 digests for `ao`, `ao-policy`, and `ao-worker`.

## Ubuntu Coordinator

Start the coordinator on loopback port `50051` and keep it local to the host:

```sh
cd /path/to/ao-runtime
export AO_HOME="${AO_HOME:-$HOME/.ao}"
ao init
ao daemon start --foreground
```

In a production service install, use the `ao-runtime/deploy/ubuntu`
systemd assets for the local worker. Keep coordinator bind addresses on
`127.0.0.1`; Mac and Windows reach it through SSH tunnels.

AO Runtime also supports daemon-owned coordinator TLS/mTLS from
`AO_HOME/config.toml` when a non-loopback coordinator endpoint is intentionally
exposed:

```toml
[coordinator]
enabled = true
bind = "0.0.0.0:50051"

[coordinator.tls]
cert = "/etc/ao-runtime/tls/coordinator.pem"
key = "/etc/ao-runtime/tls/coordinator.key"
mtls_ca = "/etc/ao-runtime/tls/worker-client-ca.pem"
```

The same paths can be resolved through env-var-name fields:

```toml
[coordinator.tls]
cert_env = "AO_DAEMON_COORDINATOR_TLS_CERT"
key_env = "AO_DAEMON_COORDINATOR_TLS_KEY"
mtls_ca_env = "AO_DAEMON_COORDINATOR_MTLS_CA"
```

For v0.2 Mac/Windows lanes, prefer loopback plus authenticated SSH tunnels.
Plain LAN exposure of unauthenticated write-capable endpoints is forbidden.

If direct-network WAL replication is required and SSH tunnels are not viable,
AO Runtime supports a daemon-owned WAL HTTPS publisher. Plain WAL HTTP remains loopback-only;
network WAL publication must use `[coordinator.wal_http.tls]` and the bearer
token must stay in the named environment variable:

```toml
[coordinator.wal_http]
enabled = true
bind = "0.0.0.0:7001"
bearer_token_env = "AO_WAL_HTTP_TOKEN"

[coordinator.wal_http.tls]
cert_env = "AO_WAL_HTTP_TLS_CERT"
key_env = "AO_WAL_HTTP_TLS_KEY"
```

Worker RuntimeService endpoints are write-capable. Keep
`AO_WORKER_RUNTIME_BIND` on `127.0.0.1` for the Mac/Windows tunnel lanes. If an
operator intentionally changes that bind to a non-loopback address, AO Runtime
requires either RuntimeService TLS material such as `AO_WORKER_RUNTIME_TLS_CERT`
and `AO_WORKER_RUNTIME_TLS_KEY`, or the explicit marker
`AO_WORKER_RUNTIME_NON_LOOPBACK_AUTH=authenticated-reverse-tunnel` after the
reverse tunnel is authenticated.

Verify the coordinator listener:

```sh
ss -ltnp | grep 50051
```

## Mac Worker

Install the worker binary and launchd plist from `ao-runtime`:

```sh
sudo install -m 0755 /path/to/ao-runtime/dist/<platform>/bin/ao-worker /usr/local/bin/ao-worker
# If building directly instead of staging a release artifact:
# sudo install -m 0755 /path/to/ao-runtime/target/release/ao-worker /usr/local/bin/ao-worker
mkdir -p ~/Library/LaunchAgents
cp /path/to/ao-runtime/deploy/mac/com.aoruntime.worker.plist ~/Library/LaunchAgents/
```

Edit the plist or launchd environment for the host-specific values:

```text
AO_COORDINATOR_URL=http://127.0.0.1:50051
AO_WORKER_NODE_ID=mac-worker
AO_WORKER_LABEL=Mac AO worker
AO_WORKER_ADAPTERS=codex,claude,fake
AO_WORKER_TAGS=mac,live
AO_WORKER_ENROLLMENT_TOKEN=<local enrollment token>
```

If the coordinator is served over TLS instead of through a local tunnel, use
`https://` and provide the coordinator client TLS material:

```text
AO_COORDINATOR_URL=https://<coordinator-host>:50051
AO_COORDINATOR_TLS_CA=/path/to/coordinator-ca.pem
AO_COORDINATOR_TLS_CLIENT_CERT=/path/to/worker-client.pem
AO_COORDINATOR_TLS_CLIENT_KEY=/path/to/worker-client.key
AO_COORDINATOR_TLS_DOMAIN_NAME=coordinator.internal
```

Start the tunnel from Mac to Ubuntu:

```sh
cd /path/to/ao-operator
FACTORY_V3_SSH_USER=<ubuntu-user> scripts/cross-host-tunnel.sh <ubuntu-host>
```

Start launchd:

```sh
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.aoruntime.worker.plist
launchctl kickstart -k "gui/$(id -u)/com.aoruntime.worker"
```

## Windows Worker

Install OpenSSH Client and copy or build `ao-worker.exe` into the user profile.
Create `%USERPROFILE%\.config\ao-worker.toml`:

```toml
tags = ["win"]
```

Set user environment variables:

```powershell
[Environment]::SetEnvironmentVariable("AO_COORDINATOR_URL", "http://127.0.0.1:50051", "User")
[Environment]::SetEnvironmentVariable("AO_WORKER_NODE_ID", "windows-worker", "User")
[Environment]::SetEnvironmentVariable("AO_WORKER_LABEL", "Windows AO worker", "User")
[Environment]::SetEnvironmentVariable("AO_WORKER_ADAPTERS", "codex,claude,fake", "User")
[Environment]::SetEnvironmentVariable("AO_WORKER_ENROLLMENT_TOKEN", "<local enrollment token>", "User")
```

For a TLS coordinator, use the same worker client TLS variables as Mac:

```powershell
[Environment]::SetEnvironmentVariable("AO_COORDINATOR_URL", "https://<coordinator-host>:50051", "User")
[Environment]::SetEnvironmentVariable("AO_COORDINATOR_TLS_CA", "C:\path\to\coordinator-ca.pem", "User")
[Environment]::SetEnvironmentVariable("AO_COORDINATOR_TLS_CLIENT_CERT", "C:\path\to\worker-client.pem", "User")
[Environment]::SetEnvironmentVariable("AO_COORDINATOR_TLS_CLIENT_KEY", "C:\path\to\worker-client.key", "User")
[Environment]::SetEnvironmentVariable("AO_COORDINATOR_TLS_DOMAIN_NAME", "coordinator.internal", "User")
```

Start the tunnel from Windows to Ubuntu. This is the supported direction for
MDM-managed Windows hosts: Windows initiates outbound SSH; Ubuntu does not SSH
into Windows.

```powershell
cd C:\path\to\ao-operator
.\scripts\cross-host-tunnel.ps1 <ubuntu-user>@<ubuntu-host>
```

For the v0.2 W4 live lane, Ubuntu can prepare a non-secret bootstrap bundle:

```sh
python3 scripts/prepare_windows_outbound_bootstrap.py
```

The generated PowerShell lives under
`run-artifacts/release-v0.2/windows-outbound-bootstrap/` and starts both the
outbound coordinator tunnel and the worker RuntimeService reverse forward.

Register the scheduled task from an elevated PowerShell prompt:

```powershell
schtasks /Create /TN "AO Runtime Worker" /XML C:\path\to\ao-runtime\deploy\windows\ao-worker-task.xml /F
schtasks /Run /TN "AO Runtime Worker"
```

## Verification

From each worker host, prove the tunnel reaches Ubuntu:

```sh
ssh <ubuntu-user>@<ubuntu-host> hostname
```

Then start `ao-worker` and check Ubuntu's AO worker health through the AO CLI
or event log. A healthy Mac worker advertises `mac,live`; a healthy Windows
worker advertises `win`.

On Ubuntu, AO Runtime `b5c839d0` added a host-local TLS validation:

```sh
cd /path/to/ao-runtime
bash scripts/remote_transfer_v2_tls_ubuntu_validate.sh
```

That script generates temporary PEM files, starts a daemon-owned mTLS
coordinator, and registers `ao-worker` over `https://`. It does not install
systemd or contact Mac/Windows.

From AO Operator, validate the committed Mac/Windows runbooks and bootstrap
artifacts against that TLS posture:

```sh
python3 scripts/check_cross_host_tls_posture.py
```

Finally, run a remote dry run on Ubuntu to verify AO Operator materializes host
tags:

```sh
cd /path/to/ao-operator
python3 scripts/factory_run.py \
  --brief examples/complex-app-smoke/task-brief.md \
  --slug cross-host-smoke \
  --profile evidence \
  --dry-run \
  --remote \
  --overwrite-artifacts
```

Live cross-host execution remains gated behind `AO_LIVE_CROSS_HOST=1` and
provider/worker readiness.
