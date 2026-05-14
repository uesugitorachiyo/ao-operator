#!/usr/bin/env python3
"""Ingest Agent OS role outputs from AO-produced role artifacts."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import check_agent_os_role_output_schema


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXECUTION_REPORT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-runspec-execution-report.json"
DEFAULT_ROLES_DIR = "run-artifacts/remote-transfer-v2-stress-live/roles"
DEFAULT_OUTPUT_DIR = "run-artifacts/remote-transfer-v2-stress-live/agent-os-role-outputs"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/agent-os-role-output-ingestion.json"
ACCEPTED_RESULTS = {"ACCEPTED", "DONE", "DONE_WITH_CONCERNS", "PASS"}


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    target = path.relative_to(root) if path.is_relative_to(root) else Path(path)
    return target.as_posix()


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def first_field(body: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}:\s*(.*)$", body, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def section(body: str, start: str, end: str) -> str:
    match = re.search(rf"^{re.escape(start)}:\s*\n(.*?)(?=^{re.escape(end)}:)", body, flags=re.MULTILINE | re.DOTALL)
    if not match:
        return ""
    lines = []
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            stripped = stripped[2:]
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)


def parse_role_artifact(path: Path, *, root: Path = ROOT) -> dict[str, Any]:
    body = path.read_text(encoding="utf-8")
    top = body.split("\n## Captured STATUS", 1)[0]
    role = path.stem
    return {
        "schema": "ao-operator/agent-os-role-output/v1",
        "role": role,
        "Result": first_field(top, "Result"),
        "Artifact": first_field(top, "Artifact"),
        "Evidence": section(top, "Evidence", "Concerns"),
        "Concerns": section(top, "Concerns", "Blocker"),
        "Blocker": first_field(top, "Blocker"),
        "source_artifact": relpath(root, path),
        "full_transcript": "",
    }


def discover_role_artifacts(root: Path, roles_dir: str | Path, explicit: list[str | Path] | None) -> list[Path]:
    if explicit:
        return [resolve_path(root, item) for item in explicit]
    directory = resolve_path(root, roles_dir)
    return sorted(directory.glob("*.md")) if directory.is_dir() else []


def evaluator_accepted(outputs: list[dict[str, Any]]) -> bool:
    for output in outputs:
        if output.get("role") != "evaluator-closer":
            continue
        result = str(output.get("Result") or "").strip().upper()
        blocker = str(output.get("Blocker") or "").strip().lower()
        return result in ACCEPTED_RESULTS and blocker in {"", "none"}
    return False


def ingest_role_outputs(
    *,
    root: Path = ROOT,
    execution_report: str | Path = DEFAULT_EXECUTION_REPORT,
    roles_dir: str | Path = DEFAULT_ROLES_DIR,
    role_artifacts: list[str | Path] | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    report_path = resolve_path(root, execution_report)
    report = load_json(report_path)
    output_directory = resolve_path(root, output_dir)
    artifacts = discover_role_artifacts(root, roles_dir, role_artifacts)
    outputs: list[dict[str, Any]] = []
    written: list[Path] = []
    errors: list[str] = []

    if report.get("schema") != "ao-operator/agent-os-runspec-execution-report/v1":
        errors.append("execution report schema must be ao-operator/agent-os-runspec-execution-report/v1")

    for artifact in artifacts:
        if not artifact.is_file():
            errors.append(f"role artifact missing: {relpath(root, artifact)}")
            continue
        parsed = parse_role_artifact(artifact, root=root)
        destination = output_directory / f"{parsed['role']}.json"
        write_json(destination, parsed)
        outputs.append(parsed)
        written.append(destination)

    schema_validation = check_agent_os_role_output_schema.validate_role_outputs(root=root, role_outputs=written)
    errors.extend(schema_validation.get("errors", []))
    accepted = evaluator_accepted(outputs)
    if not any(output.get("role") == "evaluator-closer" for output in outputs):
        errors.append("evaluator-closer role output is required")
    elif not accepted:
        errors.append("evaluator-closer role output is not accepted")

    report["role_outputs"] = [relpath(root, path) for path in written]
    report["evaluator_accepted"] = accepted
    report["role_outputs_ingested"] = len(written)
    if report_path.parent.exists() or report_path.is_absolute():
        write_json(report_path, report)

    return {
        "schema": "ao-operator/agent-os-role-output-ingestion/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "execution_report": relpath(root, report_path),
        "role_artifacts": [relpath(root, path) for path in artifacts],
        "role_outputs": [relpath(root, path) for path in written],
        "role_outputs_ingested": len(written),
        "evaluator_accepted": accepted,
        "schema_validation": schema_validation,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "errors": errors,
        "next_safe_command": "Run Agent OS evaluator closure contract." if not errors else "Keep Agent OS closure blocked until role outputs are accepted.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest Agent OS role outputs from AO role artifacts")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--execution-report", default=DEFAULT_EXECUTION_REPORT)
    parser.add_argument("--roles-dir", default=DEFAULT_ROLES_DIR)
    parser.add_argument("--role-artifact", action="append", default=[])
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = ingest_role_outputs(
        root=args.root,
        execution_report=args.execution_report,
        roles_dir=args.roles_dir,
        role_artifacts=args.role_artifact,
        output_dir=args.output_dir,
    )
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = relpath(args.root, output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
