#!/usr/bin/env python3
"""RunSpec to AO Runtime preflight compatibility gate.

Proves the rendered Agent OS RunSpec YAML at
``ao/runspecs/agent-os-phase-draft.yaml`` matches the AO Runtime
``RunSpec`` contract (apiVersion, RunSpec kind, TaskKind variants, DAG
shape) by extracting the canonical contract directly from
``ao-core`` source files at gate time. Five mutation cases that AO
would reject are exercised; each must FAIL preflight. The gate never
invokes the AO CLI and never dispatches providers.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNSPEC = "ao/runspecs/agent-os-phase-draft.yaml"
DEFAULT_OUTPUT = (
    "run-artifacts/remote-transfer-v2-stress-live/"
    "agent-os-runspec-ao-preflight-compatibility.json"
)
SCHEMA = "ao-operator/agent-os-runspec-ao-preflight-compatibility/v1"
AO_API_VERSION_REL = "crates/ao-core/src/api_version.rs"
AO_RUN_SPEC_REL = "crates/ao-core/src/run_spec.rs"
AO_TASK_REL = "crates/ao-core/src/task.rs"

MUTATION_CASE_IDS = (
    "wrong_api_version_refused",
    "wrong_runspec_kind_refused",
    "unknown_task_kind_refused",
    "unknown_dependency_refused",
    "dag_cycle_refused",
)


def resolve_path(root: Path, value: str | Path) -> Path:
    p = Path(value)
    return p if p.is_absolute() else root / p


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def ao_runtime_path(root: Path) -> Path:
    raw = os.environ.get("FACTORY_V3_AO_RUNTIME_PATH") or str(root.parent / "ao-runtime")
    return Path(raw).expanduser().resolve()


def _extract_enum_block(source: str, enum_name: str) -> str:
    pattern = re.compile(rf"pub\s+enum\s+{re.escape(enum_name)}\s*\{{(.*?)\}}", re.DOTALL)
    match = pattern.search(source)
    if not match:
        raise LookupError(f"AO source does not declare enum {enum_name}")
    return match.group(1)


def _enum_attr_block(source: str, enum_name: str) -> str:
    pattern = re.compile(
        rf"((?:#\[[^\]]*\]\s*)*)pub\s+enum\s+{re.escape(enum_name)}\b",
        re.DOTALL,
    )
    match = pattern.search(source)
    if not match:
        raise LookupError(f"AO source does not declare enum {enum_name}")
    return match.group(1)


def _strip_comments(text: str) -> str:
    cleaned: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        cleaned.append(stripped)
    return "\n".join(cleaned)


def _variant_entries(body: str) -> list[tuple[list[str], str]]:
    cleaned = _strip_comments(body)
    entries: list[tuple[list[str], str]] = []
    pending_attrs: list[str] = []
    for raw_line in cleaned.splitlines():
        line = raw_line.rstrip(",").strip()
        if not line:
            continue
        if line.startswith("#["):
            pending_attrs.append(line)
            continue
        name = line.split("(", 1)[0].split("{", 1)[0].strip()
        if not name:
            continue
        entries.append((pending_attrs, name))
        pending_attrs = []
    return entries


def _variant_serde_value(attrs: list[str], variant: str, *, rename_all: str | None) -> str:
    rename_pattern = re.compile(r'#\[serde\(rename\s*=\s*"([^"]+)"\)\]')
    for attr in attrs:
        match = rename_pattern.search(attr)
        if match:
            return match.group(1)
    if rename_all == "lowercase":
        return variant.lower()
    return variant


def _rename_all(attr_block: str) -> str | None:
    match = re.search(r'rename_all\s*=\s*"([^"]+)"', attr_block)
    return match.group(1) if match else None


def extract_ao_contract(ao_runtime: Path) -> dict[str, Any]:
    api_version_src = (ao_runtime / AO_API_VERSION_REL).read_text(encoding="utf-8")
    run_spec_src = (ao_runtime / AO_RUN_SPEC_REL).read_text(encoding="utf-8")
    task_src = (ao_runtime / AO_TASK_REL).read_text(encoding="utf-8")

    api_block = _extract_enum_block(api_version_src, "ApiVersion")
    api_attrs = _enum_attr_block(api_version_src, "ApiVersion")
    api_rename = _rename_all(api_attrs)
    api_variants = [
        _variant_serde_value(attrs, name, rename_all=api_rename)
        for attrs, name in _variant_entries(api_block)
    ]

    runspec_block = _extract_enum_block(run_spec_src, "RunSpecKind")
    runspec_attrs = _enum_attr_block(run_spec_src, "RunSpecKind")
    runspec_rename = _rename_all(runspec_attrs)
    runspec_kinds = [
        _variant_serde_value(attrs, name, rename_all=runspec_rename)
        for attrs, name in _variant_entries(runspec_block)
    ]

    task_block = _extract_enum_block(task_src, "TaskKind")
    task_attrs = _enum_attr_block(task_src, "TaskKind")
    task_rename = _rename_all(task_attrs)
    task_kinds = [
        _variant_serde_value(attrs, name, rename_all=task_rename)
        for attrs, name in _variant_entries(task_block)
    ]

    return {
        "api_versions": tuple(api_variants),
        "runspec_kinds": tuple(runspec_kinds),
        "task_kinds": tuple(task_kinds),
    }


def _strip_inline_comment(line: str) -> str:
    in_quote = False
    quote_char = ""
    for idx, ch in enumerate(line):
        if in_quote:
            if ch == quote_char:
                in_quote = False
        elif ch in ('"', "'"):
            in_quote = True
            quote_char = ch
        elif ch == "#":
            return line[:idx].rstrip()
    return line.rstrip()


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _coerce(token: str) -> Any:
    token = token.strip()
    if not token:
        return ""
    if token.startswith('"') and token.endswith('"') and len(token) >= 2:
        return token[1:-1]
    if token.startswith("'") and token.endswith("'") and len(token) >= 2:
        return token[1:-1]
    if token == "true":
        return True
    if token == "false":
        return False
    if token == "null":
        return None
    if re.fullmatch(r"-?\d+", token):
        return int(token)
    if re.fullmatch(r"-?\d+\.\d+", token):
        return float(token)
    return token


def _next_non_empty(lines: list[str], start: int) -> tuple[int, str]:
    for idx in range(start, len(lines)):
        cleaned = _strip_inline_comment(lines[idx])
        if cleaned.strip():
            return idx, cleaned
    return -1, ""


def parse_runspec_yaml(body: str) -> tuple[Any, list[str]]:
    errors: list[str] = []
    if "\t" in body:
        errors.append("YAML must not contain tab characters")
    for char in ('"', "'"):
        if body.count(char) % 2 != 0:
            errors.append(f"unbalanced {char} quote")
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    raw_lines = body.splitlines()
    line_index = 0

    while line_index < len(raw_lines):
        raw = raw_lines[line_index]
        cleaned = _strip_inline_comment(raw)
        if not cleaned.strip():
            line_index += 1
            continue
        indent = _indent(cleaned)
        text = cleaned[indent:]

        if text.startswith("- "):
            while stack and indent < stack[-1][0]:
                stack.pop()
            while stack and indent == stack[-1][0] and not isinstance(stack[-1][1], list):
                stack.pop()
        else:
            while stack and indent <= stack[-1][0]:
                stack.pop()
        if not stack:
            errors.append("YAML structure collapsed unexpectedly")
            return root, errors

        parent_indent, parent = stack[-1]

        if text.startswith("- "):
            item_text = text[2:].strip()
            if not isinstance(parent, list):
                errors.append("list item without list parent")
                return root, errors
            if item_text.endswith(":") or (": " not in item_text and ":" in item_text and item_text.split(":", 1)[1].strip() == ""):
                key = item_text.rstrip(":").strip()
                child: dict[str, Any] = {}
                obj = {key: child}
                parent.append(obj)
                stack.append((indent, obj))
                stack.append((indent + 2, child))
            elif ": " in item_text:
                key, _, val = item_text.partition(": ")
                obj2: dict[str, Any] = {key.strip(): _coerce(val)}
                parent.append(obj2)
                stack.append((indent, obj2))
            else:
                parent.append(_coerce(item_text))
            line_index += 1
            continue

        if ":" not in text:
            errors.append(f"line missing colon: {text!r}")
            line_index += 1
            continue
        key, _, value = text.partition(":")
        key = key.strip()
        value = value.strip()

        if isinstance(parent, list):
            errors.append("plain key under list parent")
            return root, errors

        if value == "":
            next_idx, next_line = _next_non_empty(raw_lines, line_index + 1)
            if next_idx == -1:
                parent[key] = {}
            else:
                next_indent = _indent(next_line)
                next_text = next_line[next_indent:]
                if next_indent > indent and next_text.startswith("- "):
                    child_list: list[Any] = []
                    parent[key] = child_list
                    stack.append((indent, child_list))
                else:
                    child_dict: dict[str, Any] = {}
                    parent[key] = child_dict
                    stack.append((indent, child_dict))
            line_index += 1
            continue

        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                parent[key] = []
            else:
                items = [_coerce(part.strip()) for part in inner.split(",")]
                parent[key] = items
            line_index += 1
            continue

        parent[key] = _coerce(value)
        line_index += 1

    return root, errors


def _index_tasks(parsed: Any) -> list[dict[str, Any]]:
    if not isinstance(parsed, dict):
        return []
    spec = parsed.get("spec")
    if not isinstance(spec, dict):
        return []
    tasks = spec.get("tasks")
    return tasks if isinstance(tasks, list) else []


def _detect_cycle(tasks: list[dict[str, Any]]) -> bool:
    graph: dict[str, list[str]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        tid = task.get("id")
        deps = task.get("deps") or []
        if isinstance(tid, str):
            graph[tid] = [d for d in deps if isinstance(d, str)]
    color: dict[str, int] = {tid: 0 for tid in graph}

    def visit(node: str) -> bool:
        color[node] = 1
        for nxt in graph.get(node, []):
            if nxt not in color:
                continue
            if color[nxt] == 1:
                return True
            if color[nxt] == 0 and visit(nxt):
                return True
        color[node] = 2
        return False

    return any(visit(node) for node in list(graph) if color[node] == 0)


def validate_against_contract(parsed: Any, contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(parsed, dict):
        errors.append("RunSpec root must be a mapping")
        return errors

    api_value = parsed.get("apiVersion")
    if api_value not in contract["api_versions"]:
        errors.append(
            f"apiVersion {api_value!r} is not in AO ApiVersion variants {list(contract['api_versions'])}"
        )

    kind_value = parsed.get("kind")
    if kind_value not in contract["runspec_kinds"]:
        errors.append(
            f"RunSpec kind {kind_value!r} is not in AO RunSpecKind variants {list(contract['runspec_kinds'])}"
        )

    metadata = parsed.get("metadata")
    if not isinstance(metadata, dict) or not metadata.get("name"):
        errors.append("metadata.name must be a non-empty string")

    spec = parsed.get("spec")
    if not isinstance(spec, dict):
        errors.append("spec must be a mapping")
        return errors

    tasks = spec.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        errors.append("spec.tasks must be a non-empty list")
        return errors

    seen_ids: set[str] = set()
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            errors.append(f"task[{index}] must be a mapping")
            continue
        tid = task.get("id")
        if not isinstance(tid, str) or not tid:
            errors.append(f"task[{index}].id must be a non-empty string")
            continue
        if tid in seen_ids:
            errors.append(f"task id {tid!r} duplicated")
        seen_ids.add(tid)
        kind = task.get("kind")
        if kind not in contract["task_kinds"]:
            errors.append(
                f"task {tid!r} kind {kind!r} not in AO TaskKind variants {list(contract['task_kinds'])}"
            )
        deps = task.get("deps")
        if deps is None:
            continue
        if not isinstance(deps, list):
            errors.append(f"task {tid!r} deps must be a list")
            continue

    known_ids = {t.get("id") for t in tasks if isinstance(t, dict) and isinstance(t.get("id"), str)}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        for dep in task.get("deps") or []:
            if isinstance(dep, str) and dep not in known_ids:
                errors.append(f"task {task.get('id')!r} dep {dep!r} references unknown task")

    if _detect_cycle(tasks):
        errors.append("task DAG contains a cycle")

    return errors


def _replace_first_match(body: str, pattern: re.Pattern[str], replacement: str) -> tuple[str, bool]:
    match = pattern.search(body)
    if not match:
        return body, False
    start, end = match.span()
    return body[:start] + pattern.sub(replacement, body[start:end], count=1) + body[end:], True


def mutate_yaml_body(body: str, case_id: str) -> str:
    if case_id == "wrong_api_version_refused":
        new_body, ok = _replace_first_match(
            body,
            re.compile(r"^apiVersion:\s*ao\.dev/v1\s*$", re.MULTILINE),
            "apiVersion: ao.dev/v2",
        )
        if not ok:
            raise RuntimeError("baseline RunSpec missing apiVersion: ao.dev/v1 line")
        return new_body
    if case_id == "wrong_runspec_kind_refused":
        new_body, ok = _replace_first_match(
            body,
            re.compile(r"^kind:\s*Run\s*$", re.MULTILINE),
            "kind: Job",
        )
        if not ok:
            raise RuntimeError("baseline RunSpec missing kind: Run line")
        return new_body
    if case_id == "unknown_task_kind_refused":
        new_body, ok = _replace_first_match(
            body,
            re.compile(r"^(\s+)kind:\s*agent\s*$", re.MULTILINE),
            r"\1kind: shellscript",
        )
        if not ok:
            raise RuntimeError("baseline RunSpec missing per-task kind: agent line")
        return new_body
    if case_id == "unknown_dependency_refused":
        new_body, ok = _replace_first_match(
            body,
            re.compile(r'deps:\s*\["[^"]+"\]'),
            'deps: ["agent-os-ghost-task"]',
        )
        if not ok:
            raise RuntimeError("baseline RunSpec missing inline deps list")
        return new_body
    if case_id == "dag_cycle_refused":
        new_body, ok = _replace_first_match(
            body,
            re.compile(
                r"(- id: agent-os-planner\n      kind: agent\n      )deps:\s*\[\]",
                re.MULTILINE,
            ),
            r'\1deps: ["agent-os-evaluator-closer"]',
        )
        if not ok:
            raise RuntimeError("baseline RunSpec missing planner deps line for cycle injection")
        return new_body
    raise ValueError(f"unknown mutation case {case_id}")


def evaluate(body: str, contract: dict[str, Any]) -> dict[str, Any]:
    parsed, parse_errors = parse_runspec_yaml(body)
    schema_errors = (
        validate_against_contract(parsed, contract) if not parse_errors else []
    )
    errors = parse_errors + schema_errors
    return {
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "parse_error_count": len(parse_errors),
        "schema_error_count": len(schema_errors),
        "task_count": len(_index_tasks(parsed)),
        "task_ids": [t.get("id") for t in _index_tasks(parsed) if isinstance(t, dict)],
    }


def mutation_cases(body: str, contract: dict[str, Any]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for case_id in MUTATION_CASE_IDS:
        try:
            mutated = mutate_yaml_body(body, case_id)
            result = evaluate(mutated, contract)
        except Exception as exc:  # noqa: BLE001 — surface as case-level failure, not crash
            cases.append(
                {
                    "id": case_id,
                    "observed_verdict": "FAIL",
                    "error_count": 1,
                    "errors": [f"mutation_setup_error: {exc}"],
                    "dispatch_authorized": False,
                    "live_providers_run": False,
                }
            )
            continue
        cases.append(
            {
                "id": case_id,
                "observed_verdict": "PASS" if not result["errors"] else "FAIL",
                "error_count": len(result["errors"]),
                "parse_error_count": result["parse_error_count"],
                "schema_error_count": result["schema_error_count"],
                "dispatch_authorized": False,
                "live_providers_run": False,
            }
        )
    return cases


def build_report(*, root: Path, runspec: Path, ao_runtime: Path) -> dict[str, Any]:
    runspec_path = resolve_path(root, runspec)
    body = runspec_path.read_text(encoding="utf-8")
    contract = extract_ao_contract(ao_runtime)
    baseline = evaluate(body, contract)
    cases = mutation_cases(body, contract)

    case_failures = [c for c in cases if c["observed_verdict"] != "FAIL"]
    overall_pass = (
        baseline["verdict"] == "PASS"
        and not case_failures
        and len(cases) == len(MUTATION_CASE_IDS)
    )
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if overall_pass else "FAIL",
        "runspec_path": relpath(root, runspec_path),
        "ao_runtime_path": "${FACTORY_V3_AO_RUNTIME_PATH}",
        "ao_contract": {
            "api_versions": list(contract["api_versions"]),
            "runspec_kinds": list(contract["runspec_kinds"]),
            "task_kinds": list(contract["task_kinds"]),
        },
        "task_count": baseline["task_count"],
        "task_ids": baseline["task_ids"],
        "baseline_errors": baseline["errors"],
        "mutation_case_count": len(cases),
        "mutation_cases": cases,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "RunSpec is AO-preflight compatible; continue Agent OS architecture work without dispatching providers."
            if overall_pass
            else "Fix RunSpec AO-preflight compatibility blockers before continuing."
        ),
    }


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--runspec", type=Path, default=Path(DEFAULT_RUNSPEC))
    parser.add_argument("--ao-runtime", type=Path, default=None)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    ao_path = (
        args.ao_runtime.expanduser().resolve()
        if args.ao_runtime is not None
        else ao_runtime_path(args.root.resolve())
    )
    payload = build_report(root=args.root.resolve(), runspec=args.runspec, ao_runtime=ao_path)
    if args.write_output is not None:
        output = resolve_path(args.root.resolve(), args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root.resolve(), output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"verdict={payload['verdict']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
