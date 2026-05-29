#!/usr/bin/env python3
"""Install the AO Operator plugin into Claude Code and/or Codex.

Claude Code loads plugins through its marketplace + plugin manifest, so the
Claude side is a pair of host commands (printed). Codex reads custom prompts and
skills straight from `~/.codex/`, so the Codex side is an idempotent file install.

Usage:
    python3 scripts/install_plugin.py --confirm-global-install            # both
    python3 scripts/install_plugin.py --codex --confirm-global-install    # Codex only
    python3 scripts/install_plugin.py --claude                            # print Claude steps
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"
COMMANDS = PLUGIN / "commands"
SKILLS = ROOT / "skills"

CODEX_HOME = Path.home() / ".codex"
CODEX_PROMPTS = CODEX_HOME / "prompts"
CODEX_SKILLS = CODEX_HOME / "skills"

_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


def _strip_frontmatter(text: str) -> str:
    """Codex prompts have no frontmatter convention; drop the YAML header."""
    return _FRONTMATTER.sub("", text, count=1).lstrip("\n")


def install_codex() -> list[str]:
    actions: list[str] = []

    # Custom prompts: copy each command body (frontmatter stripped) to ~/.codex/prompts.
    CODEX_PROMPTS.mkdir(parents=True, exist_ok=True)
    for cmd in sorted(COMMANDS.glob("*.md")):
        body = _strip_frontmatter(cmd.read_text(encoding="utf-8"))
        target = CODEX_PROMPTS / cmd.name
        target.write_text(body, encoding="utf-8")
        actions.append(f"prompt {target}")

    # Skills: symlink each SKILL.md skill into ~/.codex/skills (copy on failure).
    CODEX_SKILLS.mkdir(parents=True, exist_ok=True)
    for skill_dir in sorted(SKILLS.iterdir()):
        if not (skill_dir / "SKILL.md").is_file():
            continue
        target = CODEX_SKILLS / skill_dir.name
        if target.is_symlink() or target.exists():
            if target.is_symlink() and target.resolve() == skill_dir.resolve():
                actions.append(f"ok {target}")
                continue
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
        try:
            target.symlink_to(skill_dir, target_is_directory=True)
            actions.append(f"linked {target} -> {skill_dir}")
        except OSError:
            shutil.copytree(skill_dir, target)
            actions.append(f"copied {target} (symlink unavailable)")

    return actions


def claude_steps() -> list[str]:
    return [
        "Claude Code install (run inside Claude Code):",
        f"  /plugin marketplace add {ROOT}",
        "  /plugin install ao-operator@ao-operator",
        "",
        "Then /ao-run, /ao-render, /ao-providers, /ao-profiles, /ao-intake and the",
        "ao-* role subagents are available. Skills load automatically with the plugin.",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", action="store_true", help="install the Codex side only")
    parser.add_argument("--claude", action="store_true", help="print the Claude Code steps only")
    parser.add_argument(
        "--confirm-global-install",
        action="store_true",
        help="required for the Codex file install (writes under ~/.codex)",
    )
    args = parser.parse_args()

    do_codex = args.codex or not args.claude
    do_claude = args.claude or not args.codex

    if do_codex:
        if not args.confirm_global_install:
            print("Refusing to write ~/.codex without --confirm-global-install")
            return 2
        for action in install_codex():
            print(action)
        if do_claude:
            print("")

    if do_claude:
        for line in claude_steps():
            print(line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
