# Native Cross-Platform Coworking

AO Operator is not limited to one laptop and it is not Linux-only. The public
stack is designed for native macOS, Ubuntu, and Windows collaboration.

The important claim: **Windows can participate as native Windows, not only
through WSL.**

![AO Operator native cross-platform coworking](../../images/ao-operator-cross-platform-cowork.svg)

## Why This Matters

Many agent tools look fine on one developer machine but fall apart when the work
depends on OS-specific behavior:

- launchd behavior on macOS;
- systemd and service packaging on Ubuntu;
- PowerShell, paths, scheduled tasks, and native browser behavior on Windows;
- Safari/WebKit versus Chromium/Edge checks;
- local provider CLI auth that must stay on the host where it is logged in.

AO Operator treats those machines as coworkers. The role graph decides what
needs to happen, then AO Runtime workers can execute the right roles on the
right host.

## Supported Public Story

| Host | What it is good for | Example role lane |
| --- | --- | --- |
| Ubuntu | coordinator, release packaging, service validation, CI-style checks | release captain, Linux verifier, evidence collector |
| macOS | launchd, Keychain, Safari/WebKit, desktop UX checks | Mac verifier, browser QA, provider validation |
| Windows | native PowerShell, scheduled task, path, Edge, and non-WSL behavior | Windows verifier, installer smoke, native bug reproduction |

Windows support is not "run Linux in WSL." The documented lane uses native
PowerShell and Windows-initiated outbound SSH tunnels when inbound access is
blocked by policy.

## How It Works

```text
brief or SDD
  -> AO Operator profile
  -> role graph
  -> RunSpec with host tags
  -> AO Runtime workers on Ubuntu, macOS, Windows
  -> evidence returned to the run
```

Provider authentication stays local. If a Windows machine has Codex CLI or
Claude Code logged in, the Windows worker uses that local login. AO Operator
does not require provider API keys to be shipped through another service.

## What To Try First

Start with a provider-free role graph:

```bash
bash scripts/ingest_spec_demo.sh examples/ingestible-specs/bug-fix-sdd.md bug-fix
```

For the simplest three-OS setup prompt, use the copy-pasteable SDD:

![AO Operator three OS setup prompt](../../images/ao-operator-three-os-setup.svg)

```bash
bash scripts/ingest_spec_demo.sh examples/ingestible-specs/three-os-setup-sdd.md smoke-test
```

Then read the operational runbook:

```text
docs/cross-host-setup.md
```

Use that runbook when you are ready to enroll Mac and native Windows workers.

When the three hosts are reachable, collect provider-free proof from all lanes:

```bash
python3 scripts/run_three_os_setup_smoke.py \
  --ubuntu-target <ubuntu-user>@<ubuntu-host> \
  --ubuntu-identity ~/.ssh/<ubuntu-key> \
  --windows-target <windows-user>@<windows-host> \
  --windows-identity ~/.ssh/<windows-key>
```

That writes redacted evidence under `run-artifacts/three-os-setup/`:

- `ubuntu-evidence.md`
- `mac-evidence.md`
- `windows-evidence.md`
- `three-os-setup-report.md`
- `three-os-setup-report.json`

## Good Demo Claims

The cross-platform story is strongest when shown through concrete tasks:

- one brief creates Linux, macOS, and Windows verification lanes;
- Windows reproduces a path or PowerShell bug that Linux cannot see;
- Mac validates Safari/WebKit behavior while Ubuntu runs baseline Playwright;
- release evidence shows all three hosts participated.

That is why this matters commercially: AO Operator is not just an agent prompt
wrapper. It is a local operator for coordinated work across the machines your
product actually supports.
