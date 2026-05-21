# Windows Live Validation Progress

Date: 2026-05-09
Operator: Windows Codex
Status: PASS - Windows outbound SSH tunnel and AO worker registration are proven, with W4 dispatch and provider-backed Codex dispatch also complete against the `crane` Ubuntu route.

## Scope

Continue v0.2 W4 from `origin/main` without changing AO source or provider
credentials:

- read `run-artifacts/release-v0.2/LIVE-VALIDATION.md`
- execute the Windows side of
  `run-artifacts/release-v0.2/windows-outbound-bootstrap/`
- keep provider API-key paths out of the run
- stop on live registration blockers

## Evidence

| Check | Result | Evidence |
| --- | --- | --- |
| Factory checkout | PASS | `ao-operator` was on `main` at `a69609a5` before creating this evidence branch. |
| Forbidden provider API-key env vars | PASS | `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` were absent from the Windows process environment. |
| AO Runtime freshness | PASS | Local `C:\workspace\ao-runtime` was fast-forwarded to `origin/main` at `b7b87a9`. |
| Windows worker binary | PASS | `cargo build --release -p ao-cli --bin ao-worker` completed after adding the installed `protoc.exe` directory to `PATH`; `ao-worker.exe` was copied to `%USERPROFILE%\.cargo\bin\ao-worker.exe`. |
| Worker binary smoke | PASS | `ao-worker` starts far enough to require runtime env and reports a coordinator transport error when intentionally pointed at `127.0.0.1:1`. |
| Ubuntu host discovery | PASS | `${FACTORY_V3_REMOTE_HOST}` accepts the existing Windows SSH key and returns hostname `nucx-NUC11BTMi7`. |
| Candidate stale IPs | PASS | Redacted private-network candidates did not provide the usable Ubuntu SSH path from Windows in this run. |
| Outbound tunnel | PASS | Windows-started SSH tunnel to `${FACTORY_V3_REMOTE_HOST}` launched with `-L 50051:127.0.0.1:50051` and `-R 60053:127.0.0.1:60053`. |
| Coordinator reachability through tunnel | PASS | While the tunnel was running, Windows `127.0.0.1:50051` accepted TCP, proving the Ubuntu coordinator path is reachable from Windows. |
| Crane Ubuntu route | PARTIAL | The operator-supplied `crane@${FACTORY_V3_REMOTE_HOST}` route is reachable on TCP/22 from Windows after refreshing the stale known-host entry. SSH authentication rejects both the default Windows identities and `%USERPROFILE%\.ssh\factory_v3_windows_to_ubuntu_ed25519`. |
| Crane route key fingerprint | INFO | Existing Windows factory key fingerprint: `SHA256:rDYTCVzIagdLEh3VW3chTYinbU5cGELZQzptQYcFNNs` (`ED25519`). |
| Crane route retry after Ubuntu branch read | BLOCKED | After Ubuntu Codex read the lane, Windows retried `crane@${FACTORY_V3_REMOTE_HOST}` with the factory key. TCP/22 timed out. Local ARP still had an entry for the host, while other private-network SSH candidates continued to accept TCP/22. |
| Crane route second retry | PARTIAL | TCP/22 is reachable again from Windows, but OpenSSH debug shows the Windows factory key is offered and not accepted for `crane`. Default Windows identities are also rejected. |
| Crane credential bootstrap | PASS | One credential-auth SSH session was used only to append the existing Windows factory public key to `crane`'s `authorized_keys`; subsequent SSH uses key auth. |
| Crane key auth | PASS | `ssh -i %USERPROFILE%\.ssh\factory_v3_windows_to_ubuntu_ed25519 crane@${FACTORY_V3_REMOTE_HOST} hostname` returns `crane-NUCXI7`. |
| Crane AO toolchain | PASS | User-space Rust and local `protoc` were installed on `crane`; `cargo build --release -p ao-cli --bin ao --bin ao-worker` completed in the AO Runtime checkout. |
| Crane coordinator | PASS | Temporary AO home `/tmp/ao-win-live-home` was initialized, `[coordinator] enabled = true` with `bind = "127.0.0.1:50051"`, and Ubuntu `ss` showed `127.0.0.1:50051` listening. |
| Windows outbound tunnel to Crane | PASS | Windows-started tunnel to `crane@${FACTORY_V3_REMOTE_HOST}` kept `127.0.0.1:50051` reachable locally and exposed Windows worker runtime back to Ubuntu on `127.0.0.1:60053`. |
| Windows worker registration | PASS | `ao-worker.exe` stayed running with node id `windows-live-worker`, tag `win`, runtime bind `127.0.0.1:60053`, and stdout `ao-worker: registered; heartbeat interval=10s`. |
| W4 dispatch proof | PASS | Ubuntu-side dispatch of a Windows-tagged validator job reported `run-w4-windows-dispatch-proof-20260510b` / `task-w4-windows-dispatch-proof-20260510b` completed on `windows-live-worker` and returned marker artifact `WINDOWS_W4_DISPATCH_OK`. |
| Windows Codex PATH | PASS | Windows has `codex-cli 0.129.0`; a stable `%USERPROFILE%\.cargo\bin\codex.cmd` shim forwards to `%APPDATA%\npm\codex.cmd`, and the bootstrap now prepends `%APPDATA%\npm` plus `%USERPROFILE%\.cargo\bin` before starting `ao-worker.exe`. |
| Fresh PATH-fixed registration | PASS | After restarting the Windows side, the Ubuntu coordinator WAL recorded a fresh `register` for `windows-live-worker` at `2026-05-10T23:17:55Z` with adapters `codex,claude,fake`, runtime URL `http://127.0.0.1:60053`, and tag `win`. |
| Windows Codex executable forwarder | PASS | `%USERPROFILE%\.cargo\bin\codex.exe` now exists as a real executable forwarder to `%APPDATA%\npm\codex.cmd`; both `codex.exe --version` and `codex.cmd --version` return `codex-cli 0.129.0`. |
| Provider-backed Windows Codex smoke | PASS | Ubuntu dispatched `run-windows-codex-path-proof-20260510b` / `task-windows-codex-path-proof-20260510b` to `windows-live-worker`; final status was `completed`, the coordinator WAL recorded completion at `2026-05-10T23:22:03Z`, and the returned artifact contains `WINDOWS_CODEX_PATH_OK`. |

## Blocker

No current network blocker for Windows-initiated SSH tunnel, worker
registration, W4 dispatch proof, Codex CLI discovery, or provider-backed Codex
dispatch on the Windows worker.

## Next Safe Command

With the temporary AO home active on Ubuntu and the Windows worker registered,
Ubuntu can dispatch Windows-tagged validator or provider-backed Codex jobs to
host tag `win`. To restart the Windows side only:

```powershell
$env:FACTORY_V3_UBUNTU_TARGET = "crane@${FACTORY_V3_REMOTE_HOST}"
powershell -NoProfile -ExecutionPolicy Bypass -File docs\status\release-v0.2\windows-outbound-bootstrap\bootstrap-windows-worker.ps1
```

Expected result: the script returns JSON with `verdict: STARTED`, node id
`windows-live-worker`, tags `win`, and process ids for the tunnel and worker.
Ubuntu should then observe the registered worker tagged `win`.
