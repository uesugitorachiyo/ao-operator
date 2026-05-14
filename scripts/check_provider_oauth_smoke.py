#!/usr/bin/env python3
"""Record local OAuth CLI readiness for AO Operator providers.

This gate intentionally does not dispatch live provider work. It verifies the
release-prep boundary that provider authentication is local CLI/OAuth based and
that forbidden API-key environment variables are absent.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ao-operator/provider-oauth-smoke/v1"
STATUS_ROOT = "run-artifacts/release-v0.7/provider-smoke"
DEFAULT_JSON_OUTPUT = f"{STATUS_ROOT}/provider-oauth-smoke.json"
DEFAULT_MD_OUTPUT = f"{STATUS_ROOT}/provider-oauth-smoke.md"
FORBIDDEN_ENV = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")


PROVIDERS = {
    "codex": {
        "binary": "codex",
        "version_args": ["--version"],
        "auth_marker": ".codex/auth.json",
    },
    "claude": {
        "binary": "claude",
        "version_args": ["--version"],
        "auth_marker": ".claude/.credentials.json",
    },
}


def _home_path(home: Path, relpath: str) -> Path:
    return home / relpath


def _display_home_path(path: Path, home: Path) -> str:
    try:
        return "~/" + path.relative_to(home).as_posix()
    except ValueError:
        return path.as_posix()


def _run_version(binary: str, args: list[str], *, path: str | None, home: Path) -> dict[str, Any]:
    found = shutil.which(binary, path=path)
    if not found:
        return {
            "binary_found": False,
            "binary_path": None,
            "version_status": "SKIPPED",
            "version": None,
        }
    completed = subprocess.run(
        [found, *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    output = (completed.stdout or completed.stderr).strip().splitlines()
    return {
        "binary_found": True,
        "binary_path": _display_home_path(Path(found), home),
        "version_status": "PASS" if completed.returncode == 0 and output else "FAIL",
        "version": output[0] if output else "",
    }


def build_report(
    *,
    root: Path = ROOT,
    home: Path | None = None,
    env: dict[str, str] | None = None,
    path: str | None = None,
    selected_providers: list[str] | None = None,
) -> dict[str, Any]:
    home = (home or Path.home()).resolve()
    env = dict(os.environ if env is None else env)
    path = path if path is not None else env.get("PATH")

    forbidden_env = {
        key: {"present": key in env, "status": "FAIL" if key in env else "PASS"}
        for key in FORBIDDEN_ENV
    }
    providers: dict[str, Any] = {}
    errors: list[str] = []

    provider_names = selected_providers or list(PROVIDERS)
    unknown = sorted(set(provider_names) - set(PROVIDERS))
    if unknown:
        errors.append(f"unknown_provider:{','.join(unknown)}")
        provider_names = [provider for provider in provider_names if provider in PROVIDERS]

    for provider in provider_names:
        config = PROVIDERS[provider]
        version = _run_version(
            str(config["binary"]),
            list(config["version_args"]),
            path=path,
            home=home,
        )
        auth_marker = _home_path(home, str(config["auth_marker"]))
        auth_marker_exists = auth_marker.is_file()
        entry = {
            "provider": provider,
            **version,
            "auth_marker": _display_home_path(auth_marker, home),
            "auth_marker_exists": auth_marker_exists,
            "auth_status": "PASS" if auth_marker_exists else "FAIL",
        }
        providers[provider] = entry
        if not entry["binary_found"]:
            errors.append(f"missing_cli:{provider}")
        if entry["version_status"] != "PASS":
            errors.append(f"version_check_failed:{provider}")
        if not auth_marker_exists:
            errors.append(f"missing_auth_marker:{provider}")

    for key, result in forbidden_env.items():
        if result["present"]:
            errors.append(f"forbidden_env_present:{key}")

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "verdict": "PASS" if not errors else "FAIL",
        "dispatch_authorized": False,
        "live_providers_run": False,
        "root": ".",
        "selected_providers": provider_names,
        "forbidden_env": forbidden_env,
        "providers": providers,
        "errors": errors,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Provider OAuth Smoke",
        "",
        f"Generated: {report['generated_at']}",
        f"Verdict: {report['verdict']}",
        "",
        "This artifact verifies local provider CLI/OAuth readiness without dispatching live provider work.",
        "",
        "## Provider Checks",
        "",
        "| Provider | CLI | Version | Auth marker | Status |",
        "| --- | --- | --- | --- | --- |",
    ]
    for provider in report["selected_providers"]:
        item = report["providers"][provider]
        cli = "PASS" if item["binary_found"] and item["version_status"] == "PASS" else "FAIL"
        auth = "PASS" if item["auth_marker_exists"] else "FAIL"
        status = "PASS" if cli == "PASS" and auth == "PASS" else "FAIL"
        lines.append(
            "| {provider} | {cli} | `{version}` | `{auth_marker}` ({auth}) | {status} |".format(
                provider=provider,
                cli=cli,
                version=item.get("version") or "",
                auth_marker=item["auth_marker"],
                auth=auth,
                status=status,
            )
        )
    lines.extend(
        [
            "",
            "## API-Key Boundary",
            "",
            "| Env var | Status |",
            "| --- | --- |",
        ]
    )
    for key in FORBIDDEN_ENV:
        status = report["forbidden_env"][key]["status"]
        lines.append(f"| `{key}` | {status} |")
    lines.extend(
        [
            "",
            "## Dispatch",
            "",
            f"- `dispatch_authorized`: `{str(report['dispatch_authorized']).lower()}`",
            f"- `live_providers_run`: `{str(report['live_providers_run']).lower()}`",
        ]
    )
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- `{error}`" for error in report["errors"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check local provider OAuth readiness")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-json", nargs="?", const=DEFAULT_JSON_OUTPUT, type=Path)
    parser.add_argument("--write-md", nargs="?", const=DEFAULT_MD_OUTPUT, type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--provider", action="append", choices=sorted(PROVIDERS), help="Provider to check. Repeat to check multiple providers. Defaults to all providers.")
    args = parser.parse_args(argv)

    report = build_report(root=args.root, selected_providers=args.provider)
    if args.write_json is not None:
        output = args.write_json if args.write_json.is_absolute() else args.root / args.write_json
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report["json_output"] = str(output)
    if args.write_md is not None:
        output = args.write_md if args.write_md.is_absolute() else args.root / args.write_md
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_markdown(report), encoding="utf-8")
        report["markdown_output"] = str(output)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(report["verdict"])
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
