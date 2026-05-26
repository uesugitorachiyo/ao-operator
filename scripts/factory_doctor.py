#!/usr/bin/env python3
"""AO Operator local environment doctor."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

import factory_queue


ROOT = Path(__file__).resolve().parents[1]
AO_RUNTIME_DEFAULT = (ROOT / ".." / "ao-runtime").resolve()

ROLES = {
    "planner": "FACTORY_V3_PLANNER_PROVIDER",
    "spec-forge": "FACTORY_V3_SPEC_FORGE_PROVIDER",
    "ralph-loop": "FACTORY_V3_RALPH_LOOP_PROVIDER",
    "plan-hardener": "FACTORY_V3_PLAN_HARDENER_PROVIDER",
    "factory-manager": "FACTORY_V3_FACTORY_MANAGER_PROVIDER",
    "implementer": "FACTORY_V3_IMPLEMENTER_PROVIDER",
    "slice-reviewer": "FACTORY_V3_SLICE_REVIEWER_PROVIDER",
    "integrator": "FACTORY_V3_INTEGRATOR_PROVIDER",
    "evaluator-closer": "FACTORY_V3_EVALUATOR_CLOSER_PROVIDER",
}

VALID_PROVIDERS = {"claude", "codex", "antigravity"}
FORBIDDEN_ENV = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]


def _is_windows() -> bool:
    return os.name == "nt"


def _ao_binary_candidate(ao_runtime: Path) -> Path:
    release_dir = ao_runtime / "target" / "release"
    candidate_names = ("ao.exe", "ao") if _is_windows() else ("ao",)
    return next(
        (release_dir / name for name in candidate_names if (release_dir / name).is_file()),
        release_dir / candidate_names[0],
    )


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def selected_env(env_arg: str | None = None) -> tuple[Path | None, dict[str, str]]:
    env_path = Path(env_arg) if env_arg else ROOT / ".env"
    if not env_path.is_absolute():
        env_path = ROOT / env_path
    if env_path.is_file():
        return env_path, parse_env(env_path)
    return None, {"FACTORY_V3_DEFAULT_PROVIDER": "codex"}


def add(results: list[dict[str, str]], check_id: str, ok: bool, message: str) -> None:
    results.append({"id": check_id, "status": "ok" if ok else "fail", "message": message})


def _git_config_value(key: str) -> str:
    completed = subprocess.run(
        ["git", "config", "--get", key],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return completed.stdout.strip().lower() if completed.returncode == 0 else ""


def _git_bool_enabled(value: str) -> bool:
    return value in {"1", "true", "yes", "on"}


def _git_bool_disabled(value: str) -> bool:
    return value in {"0", "false", "no", "off"}


def run_checks(env_arg: str | None = None) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []

    for key in FORBIDDEN_ENV:
        add(
            results,
            f"env.forbidden:{key}",
            key not in os.environ,
            f"{key} is absent" if key not in os.environ else f"{key} must be unset",
        )

    env_example = parse_env(ROOT / ".env.example")
    for key, value in env_example.items():
        if key.startswith("FACTORY_V3_") and key.endswith("_PROVIDER") or key == "FACTORY_V3_DEFAULT_PROVIDER":
            add(
                results,
                f"env.example:{key}",
                value in VALID_PROVIDERS,
                f"{key}={value}",
            )

    env_path, env = selected_env(env_arg)
    default_provider = env.get("FACTORY_V3_DEFAULT_PROVIDER", "codex")
    add(
        results,
        "env.active.default_provider",
        default_provider in VALID_PROVIDERS,
        f"FACTORY_V3_DEFAULT_PROVIDER={default_provider}",
    )

    selected: dict[str, str] = {}
    for role, key in ROLES.items():
        value = env.get(key, default_provider)
        selected[role] = value
        source = env_path.name if env_path else "built-in default"
        add(
            results,
            f"env.active:{role}",
            value in VALID_PROVIDERS,
            f"{role} provider={value} from {source}",
        )

    PROVIDER_BINARIES = {
        "codex": "codex",
        "claude": "claude",
        "antigravity": "agy",
    }
    for provider in sorted(set(selected.values())):
        binary = PROVIDER_BINARIES.get(provider, provider)
        found = shutil.which(binary)
        add(
            results,
            f"cli:{provider}",
            bool(found),
            f"{binary} found at {found}" if found else f"{binary} not found on PATH",
        )

    ao_runtime = Path(os.environ.get("FACTORY_V3_AO_RUNTIME_PATH", str(AO_RUNTIME_DEFAULT)))
    add(results, "path:ao_runtime", ao_runtime.is_dir(), str(ao_runtime))
    add(results, "path:factory_root", ROOT.is_dir(), str(ROOT))
    if _is_windows():
        longpaths = _git_config_value("core.longpaths")
        add(
            results,
            "git.windows.longpaths",
            _git_bool_enabled(longpaths),
            "core.longpaths=true"
            if _git_bool_enabled(longpaths)
            else "run `git config core.longpaths true` in this repo",
        )
        filemode = _git_config_value("core.filemode")
        add(
            results,
            "git.windows.filemode",
            _git_bool_disabled(filemode),
            "core.filemode=false"
            if _git_bool_disabled(filemode)
            else "run `git config core.filemode false` in this repo",
        )
    queue_root = factory_queue.ensure_queue()
    add(results, "path:queue", queue_root.is_dir(), str(queue_root))
    for name, path in factory_queue.queue_paths(queue_root).items():
        add(results, f"path:queue/{name}", path.is_dir(), str(path))
    ao_bin = _ao_binary_candidate(ao_runtime)
    add(
        results,
        "ao.binary",
        ao_bin.is_file() or shutil.which("ao") is not None,
        str(ao_bin) if ao_bin.is_file() else f"PATH ao={shutil.which('ao')}",
    )

    codex_auth = Path.home() / ".codex" / "auth.json"
    if "codex" in selected.values():
        add(results, "auth.codex", codex_auth.is_file(), str(codex_auth))

    if "claude" in selected.values():
        add(
            results,
            "auth.claude",
            shutil.which("claude") is not None,
            "Claude Code CLI present; OAuth login must be completed interactively",
        )
        add(
            results,
            "provider.claude_live_status",
            True,
            "AO Operator resolves Claude from .env and dispatches provider: claude through AO Runtime; requires Claude CLI OAuth and a rebuilt AO binary with Claude provider support",
        )
    else:
        add(
            results,
            "provider.claude_live_status",
            True,
            "No active Claude live tasks selected",
        )

    if "antigravity" in selected.values():
        agy_settings = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
        add(
            results,
            "auth.antigravity",
            agy_settings.is_file(),
            f"Antigravity CLI settings present at {agy_settings}"
            if agy_settings.is_file()
            else "Antigravity CLI not initialized — run /Applications/Antigravity.app once, then `agy --help`",
        )
        add(
            results,
            "provider.antigravity_live_status",
            True,
            "AO Operator resolves antigravity from .env and dispatches provider: antigravity through AO Runtime; requires `agy` CLI auth and an AO binary built with antigravity adapter support (see ao-runtime crates/ao-daemon/src/adapter.rs)",
        )
    else:
        add(
            results,
            "provider.antigravity_live_status",
            True,
            "No active antigravity live tasks selected",
        )

    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", help="Path to provider env file; defaults to .env or built-in codex")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    results = run_checks(args.env)
    ok = all(item["status"] == "ok" for item in results)
    payload = {"verdict": "PASS" if ok else "FAIL", "checks": results}

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for item in results:
            print(f"{item['status'].upper():4} {item['id']} - {item['message']}")
        print(f"verdict={payload['verdict']}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
