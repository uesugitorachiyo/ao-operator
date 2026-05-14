#!/usr/bin/env python3
"""Validate factory intake artifacts for dispatch readiness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import tempfile
from typing import Any


VALID_CLASSIFICATIONS = {"TRIVIAL", "MODERATE", "COMPLEX"}
VALID_SHAPES = {"greenfield", "bug-fix", "refactor"}


def _non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and any(bool(item) for item in value)


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _add(errors: list[str], field: str, message: str) -> None:
    errors.append(f"{field}: {message}")


def validate_contract(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"json: invalid JSON: {exc}"]

    classification = data.get("classification")
    if classification not in VALID_CLASSIFICATIONS:
        _add(errors, "classification", "must be TRIVIAL, MODERATE, or COMPLEX")

    shape = data.get("shape")
    if shape not in VALID_SHAPES:
        _add(errors, "shape", "must be greenfield, bug-fix, or refactor")

    if not _string(data.get("problem")).strip():
        _add(errors, "problem", "must describe the user-visible problem")
    if not _non_empty_list(data.get("success_criteria")):
        _add(errors, "success_criteria", "must contain evidence-tied criteria")
    if not (_non_empty_list(data.get("constraints")) or _non_empty_list(data.get("out_of_scope"))):
        _add(errors, "constraints", "must include constraints or out_of_scope items")
    if not _non_empty_list(data.get("sensitive_fields")):
        _add(errors, "sensitive_fields", "must declare touched sensitive fields")
    if not _non_empty_list(data.get("trigger_hints")):
        _add(errors, "trigger_hints", "must declare reviewer trigger hints")

    acceptance = data.get("acceptance_criteria")
    if not _non_empty_list(acceptance):
        _add(errors, "acceptance_criteria", "must contain verification oracles")
    elif isinstance(acceptance, list):
        for index, item in enumerate(acceptance, start=1):
            if not isinstance(item, dict):
                _add(errors, f"acceptance_criteria[{index}]", "must be an object")
                continue
            if not _string(item.get("id")).strip():
                _add(errors, f"acceptance_criteria[{index}].id", "is required")
            if not _string(item.get("oracle")).strip():
                _add(errors, f"acceptance_criteria[{index}].oracle", "is required")
            if not _string(item.get("verification")).strip():
                _add(errors, f"acceptance_criteria[{index}].verification", "is required")

    slices = data.get("slices")
    if classification in {"MODERATE", "COMPLEX"} and not _non_empty_list(slices):
        _add(errors, "slices", "must be present for MODERATE or COMPLEX work")
    elif isinstance(slices, list):
        for index, item in enumerate(slices, start=1):
            if not isinstance(item, dict):
                _add(errors, f"slices[{index}]", "must be an object")
                continue
            if not _string(item.get("id")).strip():
                _add(errors, f"slices[{index}].id", "is required")
            if not _non_empty_list(item.get("reads")):
                _add(errors, f"slices[{index}].reads", "must list scoped read paths")
            if not _non_empty_list(item.get("writes")):
                _add(errors, f"slices[{index}].writes", "must list scoped write paths")
            if not _non_empty_list(item.get("verification")):
                _add(errors, f"slices[{index}].verification", "must list closure checks")

    if shape == "bug-fix":
        gates = data.get("shape_gates", {})
        gate_text = json.dumps(gates, sort_keys=True).lower() if isinstance(gates, dict) else ""
        if "reproducer" not in gate_text and "red" not in gate_text:
            _add(errors, "shape_gates", "bug-fix work must include a reproducer or red check")
        if "suspect" not in gate_text:
            _add(errors, "shape_gates", "bug-fix work must include suspect ranking")
    if shape == "refactor":
        gates = data.get("shape_gates", {})
        gate_text = json.dumps(gates, sort_keys=True).lower() if isinstance(gates, dict) else ""
        if "pinning" not in gate_text and "gate r" not in gate_text:
            _add(errors, "shape_gates", "refactor work must include Gate R pinning evidence")

    return errors


def validate_markdown(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []

    if not re.search(r"(?:\*\*)?Classification:?(?:\*\*)?\s*(TRIVIAL|MODERATE|COMPLEX)", text):
        _add(errors, "Classification", "must be explicit")
    shape_match = re.search(
        r"(?:\*\*)?Shape:?(?:\*\*)?\s*(greenfield|bug-fix|refactor)",
        text,
        flags=re.IGNORECASE,
    )
    if not shape_match:
        _add(errors, "Shape", "must be explicit")

    required_patterns = {
        "success criteria": r"success criteria|acceptance criteria|##\s+acceptance",
        "negative constraints": r"negative constraints|out of scope|do not|constraints",
        "verification": r"verification|verify|pytest|make validate|self_check|factory_doctor",
        "sensitive fields": r"sensitive fields|sensitive_fields",
        "trigger hints": r"trigger hints|trigger_hints",
    }
    for field, pattern in required_patterns.items():
        if not re.search(pattern, text, flags=re.IGNORECASE):
            _add(errors, field, "missing from intake artifact")

    if shape_match:
        shape = shape_match.group(1).lower()
        if shape == "bug-fix" and not re.search(r"reproducer|red|suspect", text, flags=re.IGNORECASE):
            _add(errors, "Gate B", "bug-fix intake must include reproducer/red check and suspects")
        if shape == "refactor" and not re.search(r"pinning|Gate R", text, flags=re.IGNORECASE):
            _add(errors, "Gate R", "refactor intake must include pinning evidence")

    return errors


def validate_path(path: Path) -> dict[str, Any]:
    if not path.is_file():
        errors = ["path: file does not exist"]
    elif path.suffix == ".json":
        errors = validate_contract(path)
    elif path.suffix.lower() in {".md", ".markdown"}:
        errors = validate_markdown(path)
    else:
        errors = ["path: unsupported artifact type; expected .json or .md"]
    return {
        "path": str(path),
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
    }


def default_paths(repo: Path) -> list[Path]:
    candidates: list[Path] = []
    for pattern in ("docs/contracts/*.json", "docs/specs/*-spec.md"):
        candidates.extend(sorted(repo.glob(pattern)))
    return candidates


def run(paths: list[Path], repo: Path) -> dict[str, Any]:
    selected = paths or default_paths(repo)
    if not selected:
        return {
            "verdict": "WARN",
            "results": [],
            "errors": [f"no intake artifacts found under {repo}"],
        }
    results = [validate_path(path) for path in selected]
    errors = [
        f"{result['path']}: {error}"
        for result in results
        for error in result["errors"]
    ]
    return {
        "verdict": "PASS" if not errors else "FAIL",
        "results": results,
        "errors": errors,
    }


def self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = root / "contract.json"
        contract.write_text(
            json.dumps(
                {
                    "classification": "MODERATE",
                    "shape": "greenfield",
                    "problem": "Need deterministic intake validation.",
                    "success_criteria": ["Intake artifacts fail closed."],
                    "constraints": ["Do not dispatch from loose prompts."],
                    "sensitive_fields": ["repo paths"],
                    "trigger_hints": ["docs"],
                    "acceptance_criteria": [
                        {
                            "id": "AC-001",
                            "oracle": "script",
                            "verification": "python3 scripts/validate_intake.py contract.json",
                        }
                    ],
                    "slices": [
                        {
                            "id": "slice-01",
                            "reads": ["skills/factory-intake/SKILL.md"],
                            "writes": ["scripts/validate_intake.py"],
                            "verification": ["python3 scripts/validate_intake.py --self-test"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        invalid = root / "invalid.json"
        invalid.write_text('{"classification": "MAYBE"}', encoding="utf-8")
        if run([contract], root)["verdict"] != "PASS":
            print("self-test: valid contract failed", file=sys.stderr)
            return 1
        if run([invalid], root)["verdict"] != "FAIL":
            print("self-test: invalid contract passed", file=sys.stderr)
            return 1
    print("OK validate_intake self-test")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate ai-teams factory intake artifacts."
    )
    parser.add_argument("paths", nargs="*", type=Path, help="contract JSON or spec Markdown paths")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="repo root for default discovery")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--self-test", action="store_true", help="run built-in self-test")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.self_test:
        return self_test()
    result = run([path.resolve() for path in args.paths], args.repo.resolve())
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(result["verdict"])
        for error in result["errors"]:
            print(error, file=sys.stderr)
    return 0 if result["verdict"] in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
