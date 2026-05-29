# AO Operator plugin

Installs the AO Operator factory — Shape-aware intake, bounded role subagents,
provider-routed orchestration, and evidence-first closure — into **Claude Code**
and **Codex**.

## What's inside

| Component | Files | Loads in |
|-----------|-------|----------|
| Commands | `commands/ao-*.md` | Claude Code slash commands / Codex prompts |
| Subagents | `agents/ao-*.md` (8 AO roles) | Claude Code subagents |
| Skills | `skills/` → repo `skills/` | Claude Code + Codex |

Commands wrap `scripts/factory_run.py`. Subagents mirror the role contracts in
`agents/*.toml`. No hooks ship in this version.

## Claude Code

```
/plugin marketplace add /path/to/ao-operator
/plugin install ao-operator@ao-operator
```

The repo root `.claude-plugin/marketplace.json` registers this `plugin/` dir.
After install: `/ao-run`, `/ao-render`, `/ao-providers`, `/ao-profiles`,
`/ao-intake`, plus the `ao-intake … ao-evaluator-closer` subagents and all skills.

## Codex

```
python3 scripts/install_plugin.py --codex --confirm-global-install
```

Copies the command bodies (frontmatter stripped) to `~/.codex/prompts/ao-*.md`
and symlinks the skills into `~/.codex/skills/`. Invoke prompts as `/ao-run`
etc. inside Codex.

## Both at once

```
python3 scripts/install_plugin.py --confirm-global-install
```

Runs the Codex file install and prints the Claude Code commands.

## Commands

| Command | Action |
|---------|--------|
| `/ao-run <brief> [slug]` | render artifacts + launch the AO team (`--run`) |
| `/ao-render <brief> [slug]` | render pre-AO artifacts only (`--render-only`) |
| `/ao-providers` | print role → provider routing (`--show-providers`) |
| `/ao-profiles` | list profiles (`--list-profiles`) |
| `/ao-intake <intent>` | Shape-aware intake → dispatch-ready brief |

## Role subagents

`ao-intake` → `ao-planner` → `ao-plan-hardener` → `ao-factory-manager` →
`ao-implementer` → `ao-slice-reviewer` → `ao-integrator` → `ao-evaluator-closer`.

Each is bounded: scoped reads/writes, exactly one STATUS block per turn, explicit
concerns and blockers, no self-approval.
