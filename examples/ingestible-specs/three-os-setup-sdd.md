# Three-OS Setup SDD: Native Mac, Ubuntu, And Windows Coworkers

## Goal

Set up one AO Operator / AO Runtime coworking topology with three native hosts:

- Ubuntu as coordinator and Linux validation lane.
- macOS as native worker for launchd, Keychain, Safari/WebKit, and provider smoke checks.
- Windows as native non-WSL worker for PowerShell, Scheduled Task, Edge, installer, and path checks.

The operator should produce a concrete setup plan and evidence checklist that a
human can run host by host.

## Values To Fill In

Replace the placeholders before live setup:

```text
Ubuntu coordinator: <ubuntu-user>@<ubuntu-host>
Ubuntu ao-runtime path: <ubuntu-ao-runtime-path>
Ubuntu ao-operator path: <ubuntu-ao-operator-path>

Mac worker: <mac-user>@<mac-host>
Mac ao-runtime path: <mac-ao-runtime-path>
Mac ao-operator path: <mac-ao-operator-path>

Windows worker: <windows-user>@<windows-host>
Windows ao-runtime path: <windows-ao-runtime-path>
Windows ao-operator path: <windows-ao-operator-path>
```

## User Impact

A user should be able to copy this document, run it through AO Operator, and get
one host-by-host setup packet instead of piecing together the cross-host docs
manually.

## Scope

- Create a three-host setup plan.
- Keep the first run provider-free and safe.
- Use Ubuntu coordinator loopback on `127.0.0.1:50051`.
- Prefer SSH tunnels over direct LAN exposure.
- Treat Windows as native Windows, not WSL.
- Produce evidence file names for all three hosts.

## Non-Goals

- No provider API keys.
- No public LAN coordinator exposure without TLS/mTLS.
- No automatic secret generation.
- No live provider execution until local CLI OAuth is verified on each host.
- No installer packaging changes.

## Required Host Lanes

| Host | Lane | Required proof |
| --- | --- | --- |
| Ubuntu | coordinator, release/package, Linux service checks | coordinator listener, `ao-worker` availability, no provider API keys |
| macOS | launchd, Keychain, Safari/WebKit, provider smoke | local OAuth state, tunnel readiness, worker tags `mac,live` |
| Windows | native PowerShell, Scheduled Task, Edge, path checks | native PowerShell output, non-WSL proof, worker tags `win,live` |

## Provider Rules

- Provider authentication must be local OAuth CLI only.
- `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` are forbidden.
- Mac uses the Mac's local `codex` or `claude` login.
- Windows uses the Windows machine's local `codex` or `claude` login.
- Ubuntu uses the Ubuntu machine's local `codex` or `claude` login.

## Role Expectations

- Intake confirms the three host targets and blocks if any placeholder remains.
- Planner turns this SDD into a host-by-host setup sequence.
- Implementer drafts exact commands for Ubuntu, Mac, and Windows.
- Reviewer checks that Windows remains native non-WSL and that API-key auth is not used.
- Integrator combines the three evidence paths into one report contract.
- Evaluator-closer accepts only if every host has a named evidence file and a next command.

## Required Output Artifacts

Create or propose these artifacts:

```text
run-artifacts/three-os-setup/ubuntu-evidence.md
run-artifacts/three-os-setup/mac-evidence.md
run-artifacts/three-os-setup/windows-evidence.md
run-artifacts/three-os-setup/three-os-setup-report.md
```

The final report must include:

- Ubuntu coordinator status.
- Mac worker status.
- Windows native non-WSL worker status.
- Local provider auth status per host.
- Confirmation that provider API-key variables are absent.
- Exact commands run or proposed.
- Blockers, if any.
- The next command to continue.

## First Safe Command

Start with a provider-free materialization:

```bash
bash scripts/ingest_spec_demo.sh examples/ingestible-specs/three-os-setup-sdd.md smoke-test
```

Then inspect:

```text
run-artifacts/ingest-three-os-setup-sdd/ingest-three-os-setup-sdd.runspec.yaml
```

Live cross-host execution should wait until `docs/cross-host-setup.md` is
completed on all three hosts.

## Provider-Free Evidence Command

Once the hosts are reachable, collect redacted setup evidence:

```bash
python3 scripts/run_three_os_setup_smoke.py \
  --ubuntu-target <ubuntu-user>@<ubuntu-host> \
  --ubuntu-identity ~/.ssh/<ubuntu-key> \
  --windows-target <windows-user>@<windows-host> \
  --windows-identity ~/.ssh/<windows-key>
```

This writes the promised `run-artifacts/three-os-setup/` evidence files without
starting live providers or exposing provider API keys.

## Acceptance Criteria

- The generated role graph includes a reviewer or closer role that checks all three hosts.
- The plan names Ubuntu, macOS, and native Windows separately.
- The Windows lane explicitly says non-WSL.
- Provider API-key auth remains forbidden.
- Evidence paths are named for all three hosts.
- The final next step points to `docs/cross-host-setup.md` for live enrollment.
