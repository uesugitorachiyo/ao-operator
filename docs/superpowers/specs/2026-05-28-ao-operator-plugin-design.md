# AO Operator Plugin — Design

Date: 2026-05-28
Status: building (autonomous lane — no approval gate per standing instruction)

## Goal

Package ao-operator / **ao-operator** as an installable plugin for both
**Claude Code** and **Codex**, so a user can install the operator's roles,
skills, and factory workflows into either host with one step.

## Today's state (what exists)

- `skills/` — 9 SKILL.md skills (factory-intake, plan-hardener, closure-verification, …).
- `agents/*.toml` — 8 AO **role contracts** (intake → planner → plan-hardener →
  factory-manager → implementer → slice-reviewer → integrator → evaluator-closer).
- `prompts/<role>/{claude.md,codex.toml}` — 18 per-provider role prompt seeds.
- `scripts/factory_run.py` — the orchestrator CLI (`--render-only`, `--run`,
  `--show-providers`, `--list-profiles`, `--brief`, `--slug`, …).
- `scripts/install_global.py` — flat **skills-only** symlink installer into
  `~/.claude/skills` and `~/.codex/skills`. Not a real plugin.

## What "plugin" means per host

| Host | Mechanism | What it loads |
|------|-----------|---------------|
| Claude Code | marketplace (`.claude-plugin/marketplace.json`) + plugin (`.claude-plugin/plugin.json`) | auto-discovers `commands/`, `agents/`, `skills/` under plugin root |
| Codex | file-drop into `~/.codex/` | custom prompts in `~/.codex/prompts/*.md`, skills in `~/.codex/skills/`, MCP/config in `config.toml` |

Codex has no marketplace; install = copy/symlink the same portable assets.

## Design

Self-contained plugin package under `plugin/`, with a repo-root marketplace
manifest pointing at it. Keeps existing root `agents/*.toml` (AO contracts, not
Claude subagents) and `skills/` untouched, so Claude Code never tries to parse
the toml contracts as subagents.

```
.claude-plugin/
  marketplace.json          # repo is a marketplace; source -> ./plugin
plugin/
  .claude-plugin/plugin.json
  commands/                 # portable slash commands (also Codex prompts)
    ao-run.md ao-render.md ao-providers.md ao-profiles.md ao-intake.md
  agents/                   # 8 Claude subagents, one per AO role contract
  skills -> ../skills       # relative symlink: single source of truth
  README.md
scripts/install_plugin.py   # one command, both hosts
```

### Commands (portable: Claude command body == Codex prompt body)

Thin wrappers over `scripts/factory_run.py`, using `$ARGUMENTS` for the brief/slug:

- `/ao-run` — render artifacts and launch the AO team on a brief.
- `/ao-render` — render pre-AO artifacts only (no launch).
- `/ao-providers` — print resolved role→provider mapping.
- `/ao-profiles` — list available profiles.
- `/ao-intake` — drive Shape-aware intake (delegates to factory-intake skill).

### Subagents

One markdown subagent per `agents/*.toml`, frontmatter `name`/`description`
mirrored from the contract, body encoding the role's scoped reads/writes,
STATUS-block discipline (`status_required = true`), and concerns/blocker rules.
Source of truth stays the toml + `prompts/<role>/claude.md`; subagents restate
the contract for the host that lacks AO's renderer.

### Hooks

**None.** Deliberate — a prior claude-hook install bricked the operator session
(`$TASK_ID`/`$COMMAND` unexpanded). v0.1 ships zero hooks.

### Installer (`scripts/install_plugin.py`)

- `--codex`  : copy `plugin/commands/*.md` → `~/.codex/prompts/ao-*.md`,
  symlink the 9 skills → `~/.codex/skills/`. Idempotent.
- `--claude` : print the two `/plugin` commands (marketplace add + install);
  Claude Code's plugin install is host-driven, not a file drop.
- default     : run the Codex file install and print the Claude commands.
- `--confirm-global-install` required (touches `~/.codex`).

## Out of scope (YAGNI)

- No MCP server bundling (factory_run.py is invoked as CLI).
- No hooks.
- No publishing to a public marketplace; local/repo marketplace only.
