#!/usr/bin/env python3
"""Validate AO Operator vendored factory skills."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
MANIFEST = ROOT / "skills.toml"
ALLOWED_FRONTMATTER = {"name", "description", "allowed-tools", "license", "metadata"}

def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: missing YAML frontmatter")
    try:
        raw = text.split("---", 2)[1]
    except IndexError as exc:
        raise ValueError(f"{path}: malformed YAML frontmatter") from exc
    data: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"')
    return data


def validate() -> list[str]:
    errors: list[str] = []
    manifest = _load_manifest(errors)
    skill_dirs = sorted(path for path in SKILLS.iterdir() if path.is_dir())
    if not skill_dirs:
        errors.append("no skills found")
        return errors

    manifest_skills = manifest.get("skills", {}) if manifest else {}
    if not isinstance(manifest_skills, dict):
        errors.append("skills.toml: [skills] must be a table")
        manifest_skills = {}

    skill_names = {path.name for path in skill_dirs}
    manifest_names = set(manifest_skills)
    for missing in sorted(skill_names - manifest_names):
        errors.append(f"skills.toml: missing skill entry for {missing}")
    for extra in sorted(manifest_names - skill_names):
        errors.append(f"skills.toml: entry has no skill directory: {extra}")

    for skill_dir in skill_dirs:
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            errors.append(f"{skill_dir}: missing SKILL.md")
            continue
        try:
            frontmatter = _frontmatter(skill_md)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if frontmatter.get("name") != skill_dir.name:
            errors.append(f"{skill_md}: name does not match directory")
        if not frontmatter.get("description"):
            errors.append(f"{skill_md}: missing description")
        extra = set(frontmatter) - ALLOWED_FRONTMATTER
        if extra:
            errors.append(f"{skill_md}: unsupported frontmatter keys: {sorted(extra)}")

        manifest_entry = manifest_skills.get(skill_dir.name, {})
        if isinstance(manifest_entry, dict):
            expected_path = f"skills/{skill_dir.name}/SKILL.md"
            if manifest_entry.get("path") != expected_path:
                errors.append(
                    f"skills.toml: {skill_dir.name}.path must be {expected_path}"
                )
            if not manifest_entry.get("repos"):
                errors.append(f"skills.toml: {skill_dir.name}.repos must not be empty")
            if not manifest_entry.get("purpose"):
                errors.append(f"skills.toml: {skill_dir.name}.purpose must not be empty")
        elif manifest_entry:
            errors.append(f"skills.toml: {skill_dir.name} entry must be a table")

    errors.extend(_validate_policy_scripts())
    return errors


def _validate_policy_scripts() -> list[str]:
    errors: list[str] = []
    for script_name in ("validate_intake.py", "verify_closure.py", "code_smell_analyzer.py"):
        script = ROOT / "scripts" / script_name
        if not script.is_file():
            errors.append(f"scripts/{script_name}: missing")
            continue
        try:
            completed = subprocess.run(
                [sys.executable, str(script), "--self-test"],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=20,
                check=False,
            )
        except subprocess.TimeoutExpired:
            errors.append(f"scripts/{script_name}: self-test timed out")
            continue
        if completed.returncode != 0:
            errors.append(
                "scripts/{}: self-test failed: {}".format(
                    script_name,
                    (completed.stderr or completed.stdout).strip(),
                )
            )
    return errors


def _load_manifest(errors: list[str]) -> dict:
    if not MANIFEST.is_file():
        errors.append("skills.toml: missing")
        return {}
    try:
        manifest = _parse_simple_toml(MANIFEST.read_text(encoding="utf-8"))
    except ValueError as exc:
        errors.append(f"skills.toml: invalid TOML: {exc}")
        return {}
    globals_table = manifest.get("globals", {})
    if not isinstance(globals_table, dict):
        errors.append("skills.toml: [globals] must be a table")
        return manifest
    expected_targets = ["~/.claude/skills", "~/.codex/skills"]
    if globals_table.get("target_dirs") != expected_targets:
        errors.append(f"skills.toml: globals.target_dirs must be {expected_targets}")
    expected_install = "python scripts/install_global.py --confirm-global-skill-install"
    if globals_table.get("install_command") != expected_install:
        errors.append("skills.toml: globals.install_command is stale")
    if globals_table.get("validate_command") != "python scripts/validate.py":
        errors.append("skills.toml: globals.validate_command is stale")
    return manifest


def _parse_simple_toml(text: str) -> dict:
    """Parse the small subset of TOML used by skills.toml."""
    root: dict = {}
    current: dict | None = None
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            parts = [part.strip() for part in line[1:-1].split(".") if part.strip()]
            if not parts:
                raise ValueError(f"line {line_no}: empty table")
            current = root
            for part in parts:
                current = current.setdefault(part, {})
                if not isinstance(current, dict):
                    raise ValueError(f"line {line_no}: table conflicts with scalar")
            continue
        if current is None or "=" not in line:
            raise ValueError(f"line {line_no}: expected table or key/value")
        key, raw_value = [part.strip() for part in line.split("=", 1)]
        current[key] = _parse_simple_value(raw_value, line_no)
    return root


def _parse_simple_value(raw: str, line_no: int) -> str | list[str]:
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        values: list[str] = []
        for item in inner.split(","):
            item = item.strip()
            if not (item.startswith('"') and item.endswith('"')):
                raise ValueError(f"line {line_no}: list items must be strings")
            values.append(item[1:-1])
        return values
    raise ValueError(f"line {line_no}: unsupported value")


def main() -> int:
    errors = validate()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("OK factory skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
