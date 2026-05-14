# AO Operator — Setup

> GitHub repo slug: `ao-operator`. Legacy compatibility slug: `ao-operator`.
> Env vars like `FACTORY_V3_*` are kept as wire-format identifiers.

For operator release installation, verification, troubleshooting, security
posture, and explicit non-claims, see
[`docs/private-operator-release.md`](docs/private-operator-release.md).

## Paths

AO Operator expects this local source dependency:

```text
${FACTORY_V3_AO_RUNTIME_PATH}
```

AO Runtime is not vendored into this scaffold.

No separate `ai-teams` checkout is required to run AO Runtime Operator. The
ai-teams discipline is encoded in this repo as profiles, role contracts, skills,
prompt templates, and evaluator closure rules.

## Windows Native Setup

Native Windows validation needs the same AO Runtime source checkout, plus the
Windows Rust/MSVC toolchain and archive helpers:

```powershell
git config core.longpaths true
git config core.filemode false
winget install --id Rustlang.Rustup --exact
winget install --id Microsoft.VisualStudio.2022.BuildTools --exact --override "--wait --quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --norestart"
winget install --id Google.Protobuf --exact
winget install --id Meta.Zstandard --exact
```

For a PowerShell validation session, prepend the installed tools and the AO
release directory to `PATH`:

```powershell
$ProtocDir = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\Google.Protobuf_Microsoft.Winget.Source_8wekyb3d8bbwe\bin"
$ZstdRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\Meta.Zstandard_Microsoft.Winget.Source_8wekyb3d8bbwe"
$ZstdDir = Get-ChildItem $ZstdRoot -Directory | Where-Object Name -like "zstd-*-win64" | Select-Object -First 1 -ExpandProperty FullName
$AoRelease = Join-Path $env:FACTORY_V3_AO_RUNTIME_PATH "target\release"
$env:PATH = "$env:USERPROFILE\.cargo\bin;$ProtocDir;$ZstdDir;$AoRelease;$env:PATH"
$env:PROTOC = Join-Path $ProtocDir "protoc.exe"
```

Build AO Runtime from a Visual Studio developer environment before running
`factory_doctor.py`:

```powershell
Set-Location $env:FACTORY_V3_AO_RUNTIME_PATH
cmd /d /c "call ""%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"" && cargo build --release -p ao-cli --bin ao --bin ao-worker"
```

On Windows, use `python` or the current interpreter path for local commands.
The runner resolves internal Python subprocesses from `sys.executable`, with
`FACTORY_V3_PYTHON` available as an explicit override when needed.

## Provider Auth

Use local CLI OAuth only.

For Codex:

```bash
codex login
```

For Claude Code:

```bash
claude
```

Do not configure provider API keys. `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`
are treated as forbidden environment state by `scripts/factory_doctor.py`.

## Configure Providers

Create a local `.env`:

```bash
cp .env.example .env
```

Provider values must be `claude` or `codex`.

The first smoke path defaults to Codex. If `.env` is absent, scripts use Codex
as the built-in provider default for live smoke rendering.

Topology-specific roles such as `FACTORY_V3_SPEC_FORGE_PROVIDER` and
`FACTORY_V3_RALPH_LOOP_PROVIDER` also resolve from `.env`. They must use local
OAuth CLI providers, just like the baseline roles.

Each topology task can also have an exact override, such as
`FACTORY_V3_BACKEND_FACTORY_PROVIDER=claude`. See
`examples/provider-profiles/` for all-Codex, all-Claude, and mixed examples.

## Skills

AO Operator vendors the shared factory skills under `skills/` and
tracks them in `skills.toml`.

Validate the local skill package:

```bash
python3 scripts/validate.py
```

Install them globally for both Claude Code and Codex when you want the same
skills available outside this checkout:

```bash
python3 scripts/install_global.py --confirm-global-skill-install
```

Do not run the global installer when you want the existing ai-teams-tuned
global skills to remain active.

## External Knowledge

AO Operator does not have a default llm-wiki discovery path, qmd
check, or knowledge-promotion loop. The `llm-wiki-lookup` skill remains available only for
manual lookup when a user explicitly asks for it. Planning, contracts, tests,
and dispatch gates must stand on local repo evidence.

## Validate

```bash
python3 scripts/validate_scaffold.py
python3 scripts/factory_doctor.py
python3 scripts/render_runspec.py --output /tmp/ao-operator-smoke.yaml
python3 scripts/factory_run.py --brief examples/complex-app-smoke/task-brief.md --slug complex-app-smoke --dry-run
python3 scripts/validate_factory.py --slug complex-app-smoke
python3 scripts/factory_doctor.py --env examples/claude-full/provider.env
```

To validate the factory-of-factories example with Spec Forge, Ralph Loop, and
five parallel factory branches:

```bash
python3 scripts/factory_run.py --brief examples/outperform-ai-teams-fanout/task-brief.md --slug outperform-ai-teams-fanout --provider-env examples/outperform-ai-teams-fanout/provider.env --topology examples/outperform-ai-teams-fanout/ao-fanout-topology.yaml --dry-run
python3 scripts/validate_factory.py --slug outperform-ai-teams-fanout --topology examples/outperform-ai-teams-fanout/ao-fanout-topology.yaml --contract examples/outperform-ai-teams-fanout/spec-forge.contract.json
```

To run with AO after reviewing the rendered RunSpec:

```bash
AO_HOME=/tmp/ao-operator-ao ${FACTORY_V3_AO_RUNTIME_PATH}/target/release/ao run /tmp/ao-operator-smoke.yaml
```

To run the full AO Runtime Operator lifecycle and require evaluator closure:

```bash
python3 scripts/factory_run.py --brief examples/complex-app-smoke/task-brief.md --slug complex-app-smoke --run
```

To also emit and replay-verify a signed evidence pack for the live run, provide
exactly one signer. HMAC is the local/dev path; Ed25519 is the production path.
The HMAC flag is explicit for one-off runs; the environment variable is
convenient for repeated operator sessions:

```bash
export FACTORY_V3_EVIDENCE_HMAC_KEY_HEX="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"

python3 scripts/factory_run.py \
  --brief examples/complex-app-smoke/task-brief.md \
  --slug complex-app-smoke \
  --run \
  --evidence-hmac-key-hex "$FACTORY_V3_EVIDENCE_HMAC_KEY_HEX"

python3 scripts/factory_run.py \
  --brief examples/complex-app-smoke/task-brief.md \
  --slug complex-app-smoke \
  --run
```

Production Ed25519 signing uses a PEM private key and the optional
`cryptography` package. The private key never goes into the pack; the pack
stores the public verification material under `signatures/pubkey`.

```bash
python3 scripts/factory_run.py \
  --brief examples/complex-app-smoke/task-brief.md \
  --slug complex-app-smoke \
  --run \
  --evidence-ed25519-private-key ./operator-ed25519.pem

FACTORY_V3_EVIDENCE_ED25519_PRIVATE_KEY=./operator-ed25519.pem \
  python3 scripts/factory_run.py \
    --brief examples/complex-app-smoke/task-brief.md \
    --slug complex-app-smoke \
    --run
```

The runner writes:

```text
run-artifacts/<slug>/evidence-packs/evidence-pack-<run_id>/
run-artifacts/<slug>/evidence-packs/evidence-pack-<run_id>.tar.zst
run-artifacts/<slug>/evidence-packs/evidence-pack-<run_id>-summary.json
```

Replay or verify a saved pack with:

```bash
python3 scripts/factory_run.py replay \
  run-artifacts/complex-app-smoke/evidence-packs/evidence-pack-<run_id>.tar.zst \
  --hmac-key-hex "$FACTORY_V3_EVIDENCE_HMAC_KEY_HEX" \
  --write-report run-artifacts/complex-app-smoke/evidence-packs/evidence-pack-<run_id>-replay.json
```

The replay report schema is `ao-operator/evidence-pack-replay/v1`. It includes
base signature/Merkle/CAS verification, manifest task/event coverage,
transcript path checks, artifact-reference checks, and a deterministic non-LLM
replay field. When a manifest task declares `deterministic: true`, replay
validates its `replay_command`/`replay_outputs` contract and confirms the
declared outputs resolve to content-addressed artifacts. Older packs without
deterministic declarations keep reporting that field as `SKIPPED`.

Deterministic commands are never run unless the operator adds
`--execute-deterministic`; that mode runs without a shell in a temporary
working directory, with a minimal environment, network-client denylist, timeout,
and output hash comparison against CAS:

```bash
python3 scripts/factory_run.py replay \
  run-artifacts/complex-app-smoke/evidence-packs/evidence-pack-<run_id>.tar.zst \
  --hmac-key-hex "$FACTORY_V3_EVIDENCE_HMAC_KEY_HEX" \
  --execute-deterministic \
  --deterministic-timeout-seconds 5
```

For replay commands that begin with `python` or `python3`, Windows hosts resolve
the executable through the same portable interpreter path used by the runner
(`sys.executable` or `FACTORY_V3_PYTHON`). This keeps replayable packs portable
between POSIX hosts and native Windows shells where `python3.exe` is absent.

For live evidence-pack generation, pass `--evidence-execute-deterministic` with
`--run` so the saved live summary records
`checks.deterministic_command_execution == "PASS"` for deterministic tasks.
The live-summary gate fails deterministic summaries that only validate
declarations but skip execution.

Evidence-pack archive generation and archive replay require the optional `zstd`
CLI. Ed25519 requires optional `cryptography`. The readiness gate is
deterministic and does not call Codex, Claude, or AO:

```bash
python3 scripts/check_evidence_pack_readiness.py --json
python3 scripts/check_live_evidence_pack_replay.py --json
```

Claude roles resolve from `.env` and run through AO Runtime as `provider:
claude`. AO Operator does not silently substitute providers. The checked-in
Claude manifest uses Claude Code OAuth, `haiku`, JSON output, disabled tools,
project-only settings, and no session persistence for bounded AO smoke runs.
