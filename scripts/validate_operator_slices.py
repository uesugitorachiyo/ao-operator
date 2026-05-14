#!/usr/bin/env python3
"""Validate AO Operator operator slice manifests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VALID_CLASSIFICATIONS = {"TRIVIAL", "MODERATE", "COMPLEX"}
VALID_SHAPES = {"greenfield", "bug-fix", "refactor"}
DEFAULT_MAX_LIVE_TASKS = 50


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _non_empty_strings(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) and item.strip() for item in value)


def _strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)


def _add(errors: list[str], field: str, message: str) -> None:
    errors.append(f"{field}: {message}")


def _command_uses_run(command: str) -> bool:
    parts = command.split()
    return "--run" in parts


def validate_manifest_data(data: dict[str, Any], *, max_live_tasks: int | None = None) -> list[str]:
    errors: list[str] = []
    limit = max_live_tasks if max_live_tasks is not None else int(data.get("max_live_tasks_default") or DEFAULT_MAX_LIVE_TASKS)

    if data.get("schema") != "ao-operator/operator-slices/v1":
        _add(errors, "schema", "must be ao-operator/operator-slices/v1")
    if data.get("classification") not in VALID_CLASSIFICATIONS:
        _add(errors, "classification", "must be TRIVIAL, MODERATE, or COMPLEX")
    if data.get("shape") not in VALID_SHAPES:
        _add(errors, "shape", "must be greenfield, bug-fix, or refactor")
    if not _string(data.get("objective")).strip():
        _add(errors, "objective", "is required")
    if not _non_empty_strings(data.get("negative_constraints")):
        _add(errors, "negative_constraints", "must list safety constraints")
    if not _non_empty_strings(data.get("sensitive_fields")):
        _add(errors, "sensitive_fields", "must list sensitive fields")

    slices = data.get("slices")
    if not isinstance(slices, list) or not slices:
        _add(errors, "slices", "must be a non-empty list")
        return errors

    orders: list[int] = []
    ids: list[str] = []
    saw_diagnostic = False
    saw_validation = False
    saw_live = False
    for index, item in enumerate(slices):
        field = f"slices[{index}]"
        if not isinstance(item, dict):
            _add(errors, field, "must be an object")
            continue
        order = item.get("order")
        if not isinstance(order, int):
            _add(errors, f"{field}.order", "must be an integer")
        else:
            orders.append(order)
        slice_id = _string(item.get("id")).strip()
        if not slice_id:
            _add(errors, f"{field}.id", "is required")
        else:
            ids.append(slice_id)
        mode = _string(item.get("mode")).strip()
        if not mode:
            _add(errors, f"{field}.mode", "is required")
        if mode == "diagnostic":
            saw_diagnostic = True
        if mode == "validation":
            saw_validation = True
        if not _string(item.get("objective")).strip():
            _add(errors, f"{field}.objective", "is required")
        if not _strings(item.get("reads")):
            _add(errors, f"{field}.reads", "must be a list of strings")
        if not _strings(item.get("writes")):
            _add(errors, f"{field}.writes", "must be a list of strings")
        if not _non_empty_strings(item.get("commands")):
            _add(errors, f"{field}.commands", "must contain runnable command strings")
        env = item.get("env", {})
        if env is not None and not isinstance(env, dict):
            _add(errors, f"{field}.env", "must be an object when present")
        elif isinstance(env, dict):
            for key, value in env.items():
                if not isinstance(key, str) or not key.strip():
                    _add(errors, f"{field}.env", "keys must be non-empty strings")
                elif key == "PATH_PREPEND":
                    if not (
                        isinstance(value, str)
                        or (
                            isinstance(value, list)
                            and all(isinstance(entry, str) and entry.strip() for entry in value)
                        )
                    ):
                        _add(errors, f"{field}.env.PATH_PREPEND", "must be a string or list of strings")
                elif not isinstance(value, str):
                    _add(errors, f"{field}.env.{key}", "must be a string")
        if not _non_empty_strings(item.get("evidence")):
            _add(errors, f"{field}.evidence", "must list evidence outputs")
        if not _non_empty_strings(item.get("stop_rules")):
            _add(errors, f"{field}.stop_rules", "must list stop rules")
        timeout_seconds = item.get("timeout_seconds")
        if timeout_seconds is not None and (not isinstance(timeout_seconds, int) or timeout_seconds <= 0):
            _add(errors, f"{field}.timeout_seconds", "must be a positive integer when present")

        task_count = item.get("task_count")
        if not isinstance(task_count, int) or task_count < 0:
            _add(errors, f"{field}.task_count", "must be a non-negative integer")
            task_count = 0

        live_provider = item.get("live_provider") is True
        expected_blocked = item.get("expected_blocked") is True
        requires_override = item.get("requires_override") is True
        commands = item.get("commands") if isinstance(item.get("commands"), list) else []
        run_commands = [command for command in commands if isinstance(command, str) and _command_uses_run(command)]
        if live_provider:
            saw_live = True
            if not run_commands:
                _add(errors, f"{field}.commands", "live_provider slices must include a --run command")
            if task_count == 0:
                _add(errors, f"{field}.task_count", "live_provider slices must declare task_count")
        elif run_commands and not expected_blocked:
            _add(errors, f"{field}.commands", "--run is only allowed for live_provider or expected_blocked slices")

        if expected_blocked and item.get("expected_exit") != 1:
            _add(errors, f"{field}.expected_exit", "expected_blocked slices must declare expected_exit=1")
        if task_count > limit and not requires_override and not expected_blocked and live_provider:
            _add(errors, f"{field}.requires_override", f"live task_count above {limit} requires override")
        if requires_override and _string(item.get("approval_env")).strip() != "FACTORY_V3_ALLOW_LARGE_LIVE_RUN":
            _add(errors, f"{field}.approval_env", "must be FACTORY_V3_ALLOW_LARGE_LIVE_RUN")

    duplicate_orders = sorted({order for order in orders if orders.count(order) > 1})
    duplicate_ids = sorted({slice_id for slice_id in ids if ids.count(slice_id) > 1})
    if duplicate_orders:
        _add(errors, "slices.order", "duplicate orders: " + ", ".join(str(order) for order in duplicate_orders))
    if duplicate_ids:
        _add(errors, "slices.id", "duplicate ids: " + ", ".join(duplicate_ids))
    if orders and orders != sorted(orders):
        _add(errors, "slices.order", "orders must be sorted ascending")
    if not saw_diagnostic:
        _add(errors, "slices", "must include a diagnostic slice")
    if not saw_validation:
        _add(errors, "slices", "must include a validation slice")
    if not saw_live:
        _add(errors, "slices", "must include a live_provider slice")
    return errors


def validate_path(path: Path, *, max_live_tasks: int | None = None) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"path": str(path), "verdict": "FAIL", "errors": ["path: file does not exist"]}
    except json.JSONDecodeError as exc:
        return {"path": str(path), "verdict": "FAIL", "errors": [f"json: invalid JSON: {exc}"]}
    if not isinstance(data, dict):
        return {"path": str(path), "verdict": "FAIL", "errors": ["json: manifest must be an object"]}
    errors = validate_manifest_data(data, max_live_tasks=max_live_tasks)
    return {
        "path": str(path),
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "slice_count": len(data.get("slices", [])) if isinstance(data.get("slices"), list) else 0,
    }


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    return data


def slice_summaries(data: dict[str, Any], *, local_only: bool = False) -> list[dict[str, object]]:
    slices = data.get("slices", [])
    if not isinstance(slices, list):
        return []
    summaries: list[dict[str, object]] = []
    for item in slices:
        if not isinstance(item, dict):
            continue
        live_provider = item.get("live_provider") is True
        if local_only and live_provider:
            continue
        summaries.append(
            {
                "order": item.get("order"),
                "id": item.get("id"),
                "mode": item.get("mode"),
                "live_provider": live_provider,
                "expected_blocked": item.get("expected_blocked") is True,
                "requires_override": item.get("requires_override") is True,
                "task_count": item.get("task_count"),
                "env_keys": sorted(item.get("env", {}).keys()) if isinstance(item.get("env"), dict) else [],
            }
        )
    return summaries


def commands_for(data: dict[str, Any], slice_id: str) -> list[str]:
    slices = data.get("slices", [])
    if not isinstance(slices, list):
        return []
    for item in slices:
        if isinstance(item, dict) and item.get("id") == slice_id:
            commands = item.get("commands", [])
            return [command for command in commands if isinstance(command, str)]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate AO Operator operator slice manifests")
    parser.add_argument("manifest", nargs="?", default="examples/remote-transfer-v2-stress/operator-slices.json")
    parser.add_argument("--max-live-tasks", type=int, default=None)
    parser.add_argument("--list-slices", action="store_true", help="List ordered slice summaries after validation")
    parser.add_argument("--local-only", action="store_true", help="With --list-slices, omit live provider slices")
    parser.add_argument("--commands-for", help="Print commands for one validated slice id")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    path = Path(args.manifest)
    if not path.is_absolute():
        path = ROOT / path
    result = validate_path(path, max_live_tasks=args.max_live_tasks)
    data: dict[str, Any] | None = None
    if result["verdict"] == "PASS" and (args.list_slices or args.commands_for):
        try:
            data = load_manifest(path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            result = {**result, "verdict": "FAIL", "errors": [*result["errors"], f"manifest: {exc}"]}
    payload = {
        "verdict": result["verdict"],
        "results": [result],
        "errors": [f"{result['path']}: {error}" for error in result["errors"]],
    }
    if data is not None and args.list_slices:
        payload["slices"] = slice_summaries(data, local_only=args.local_only)
    if data is not None and args.commands_for:
        commands = commands_for(data, args.commands_for)
        if commands:
            payload["commands"] = commands
        else:
            payload["verdict"] = "FAIL"
            payload["errors"].append(f"{path}: slice not found: {args.commands_for}")
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"verdict={payload['verdict']}")
        for item in payload.get("slices", []):
            if isinstance(item, dict):
                print(f"{item['order']}: {item['id']} [{item['mode']}] live={item['live_provider']}")
        for command in payload.get("commands", []):
            print(command)
        for error in payload["errors"]:
            print(error)
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
