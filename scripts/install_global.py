#!/usr/bin/env python3
"""Install AO Operator factory skills into Claude and Codex global skill dirs.

The installer creates symlinks so the workspace-level `ao-operator/skills/` tree
remains the single source of truth.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
TARGETS = (
    Path.home() / ".claude" / "skills",
    Path.home() / ".codex" / "skills",
)


def install(*, copy: bool = False) -> list[str]:
    actions: list[str] = []
    for target_root in TARGETS:
        target_root.mkdir(parents=True, exist_ok=True)
        for skill_dir in sorted(SKILLS.iterdir()):
            if not (skill_dir / "SKILL.md").is_file():
                continue
            target = target_root / skill_dir.name
            if target.exists() or target.is_symlink():
                if target.is_symlink() and target.resolve() == skill_dir.resolve():
                    actions.append(f"ok {target} -> {skill_dir}")
                    continue
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            if copy:
                shutil.copytree(skill_dir, target)
                actions.append(f"copied {target}")
            else:
                try:
                    target.symlink_to(skill_dir, target_is_directory=True)
                    actions.append(f"linked {target} -> {skill_dir}")
                except OSError:
                    shutil.copytree(skill_dir, target)
                    actions.append(f"copied {target} (symlink unavailable)")
    return actions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--copy",
        action="store_true",
        help="copy skill directories instead of creating symlinks",
    )
    parser.add_argument(
        "--confirm-global-skill-install",
        action="store_true",
        help="required because this changes ~/.claude/skills and ~/.codex/skills",
    )
    args = parser.parse_args()
    if not args.confirm_global_skill_install:
        print(
            "Refusing to change global skill installs without "
            "--confirm-global-skill-install"
        )
        return 2
    for action in install(copy=args.copy):
        print(action)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
