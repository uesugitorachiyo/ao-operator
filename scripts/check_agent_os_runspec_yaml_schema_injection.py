#!/usr/bin/env python3
"""Validate Agent OS RunSpec YAML schema/format failure injection (no provider dispatch).

This gate enforces the structural schema of the committed RunSpec YAML and proves
that six byte-level malformations are refused fail-closed:

1. malformed_yaml_refused — tab characters or unbalanced quotes break parsing.
2. duplicate_task_ids_refused — two tasks share the same id.
3. missing_spec_block_refused — a task is missing its `spec:` block.
4. bad_deps_type_refused — a task's `deps` is not a list.
5. unknown_task_field_refused — a task carries an unrecognized top-level key.
6. unsafe_dispatch_authorized_refused — a task sets `dispatchAuthorized: true`.

The check parses YAML directly; it does not invoke AO Runtime or any provider CLI.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATUS_ROOT = "run-artifacts/remote-transfer-v2-stress-live"
DEFAULT_RUNSPEC = "ao/runspecs/agent-os-phase-draft.yaml"
DEFAULT_OUTPUT = f"{STATUS_ROOT}/agent-os-runspec-yaml-schema-injection.json"
SCHEMA = "ao-operator/agent-os-runspec-yaml-schema-injection/v1"

ALLOWED_TOP_KEYS = ("apiVersion", "kind", "metadata", "spec")
ALLOWED_METADATA_KEYS = ("name", "description")
ALLOWED_SPEC_KEYS = ("tasks",)
ALLOWED_TASK_KEYS = ("id", "kind", "deps", "spec")
ALLOWED_TASK_SPEC_KEYS = (
    "provider",
    "agent",
    "promptFile",
    "workspace",
    "policyProfile",
    "dispatchAuthorized",
)


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _strip_inline_comment(line: str) -> str:
    in_dq = False
    in_sq = False
    for i, ch in enumerate(line):
        if ch == '"' and not in_sq:
            in_dq = not in_dq
        elif ch == "'" and not in_dq:
            in_sq = not in_sq
        elif ch == "#" and not in_dq and not in_sq:
            if i == 0 or line[i - 1] in (" ", "\t"):
                return line[:i].rstrip()
    return line


def _indent(line: str) -> int:
    n = 0
    while n < len(line) and line[n] == " ":
        n += 1
    return n


def _coerce(value: str) -> Any:
    text = value.strip()
    if not text:
        return None
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        return text[1:-1]
    if text == "true":
        return True
    if text == "false":
        return False
    if text in ("null", "~"):
        return None
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        items: list[Any] = []
        depth = 0
        cur = ""
        for ch in inner:
            if ch == "," and depth == 0:
                token = cur.strip()
                if token:
                    items.append(_coerce(token))
                cur = ""
                continue
            if ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
            cur += ch
        token = cur.strip()
        if token:
            items.append(_coerce(token))
        return items
    return text


def parse_runspec_yaml(body: str) -> tuple[Any, list[str]]:
    """Parse the constrained RunSpec YAML.

    Returns (root_value, errors). errors collect byte/structural malformations
    detected during parsing; the parser is best-effort and continues even when
    individual lines fail.
    """

    errors: list[str] = []

    raw_lines = body.splitlines()
    for idx, raw in enumerate(raw_lines, start=1):
        if "\t" in raw:
            errors.append(f"line {idx}: tab characters disallowed (RunSpec uses spaces)")
        cleaned = _strip_inline_comment(raw)
        if cleaned.count('"') % 2 != 0:
            errors.append(f"line {idx}: unbalanced double-quote")
        if cleaned.count("'") % 2 != 0:
            errors.append(f"line {idx}: unbalanced single-quote")

    significant: list[tuple[int, str]] = []
    for idx, raw in enumerate(raw_lines, start=1):
        cleaned = _strip_inline_comment(raw).rstrip()
        if cleaned.strip():
            significant.append((idx, cleaned))

    if not significant:
        errors.append("runspec YAML is empty")
        return None, errors

    first_indent = _indent(significant[0][1])
    if first_indent != 0:
        errors.append(
            f"line {significant[0][0]}: top-level indent must be 0 (got {first_indent})"
        )

    root: dict[str, Any] = {}
    stack: list[tuple[int, Any, str]] = [(0, root, "dict")]

    def peek_next(after_index: int) -> tuple[int, str] | None:
        if after_index + 1 < len(significant):
            return significant[after_index + 1]
        return None

    i = 0
    while i < len(significant):
        idx, line = significant[i]
        ind = _indent(line)
        while stack and stack[-1][0] > ind:
            stack.pop()
        if not stack:
            errors.append(f"line {idx}: indentation drops below root")
            i += 1
            continue
        cur_indent, cur, cur_kind = stack[-1]
        if ind > cur_indent:
            errors.append(
                f"line {idx}: unexpected indent (got {ind}, expected {cur_indent})"
            )
            i += 1
            continue
        content = line[ind:]

        if content.startswith("- "):
            after = content[2:]
            if cur_kind != "list":
                errors.append(f"line {idx}: sequence item in non-sequence context")
                i += 1
                continue
            if ":" in after and not after.lstrip().startswith(("[", "{")):
                key, _, val = after.partition(":")
                key = key.strip()
                val = val.strip()
                item: dict[str, Any] = {}
                cur.append(item)
                if val:
                    item[key] = _coerce(val)
                else:
                    nxt = peek_next(i)
                    if nxt and _indent(nxt[1]) > ind + 2:
                        nxt_ind = _indent(nxt[1])
                        nxt_content = nxt[1][nxt_ind:]
                        if nxt_content.startswith("- "):
                            sub_list: list[Any] = []
                            item[key] = sub_list
                            stack.append((ind + 2, item, "dict"))
                            stack.append((nxt_ind, sub_list, "list"))
                            i += 1
                            continue
                        sub_dict: dict[str, Any] = {}
                        item[key] = sub_dict
                        stack.append((ind + 2, item, "dict"))
                        stack.append((nxt_ind, sub_dict, "dict"))
                        i += 1
                        continue
                    item[key] = None
                stack.append((ind + 2, item, "dict"))
            else:
                cur.append(_coerce(after))
            i += 1
            continue

        if ":" not in content:
            errors.append(f"line {idx}: missing ':' in mapping line")
            i += 1
            continue
        key, _, val = content.partition(":")
        key = key.strip()
        val = val.strip()
        if not key:
            errors.append(f"line {idx}: empty mapping key")
            i += 1
            continue
        if cur_kind != "dict":
            errors.append(f"line {idx}: mapping key {key!r} in non-mapping context")
            i += 1
            continue
        if val:
            cur[key] = _coerce(val)
            i += 1
            continue
        nxt = peek_next(i)
        if nxt and _indent(nxt[1]) > ind:
            nxt_ind = _indent(nxt[1])
            nxt_content = nxt[1][nxt_ind:]
            if nxt_content.startswith("- "):
                new_list: list[Any] = []
                cur[key] = new_list
                stack.append((nxt_ind, new_list, "list"))
            else:
                new_dict: dict[str, Any] = {}
                cur[key] = new_dict
                stack.append((nxt_ind, new_dict, "dict"))
        else:
            cur[key] = None
        i += 1

    return root, errors


def _check_keys(
    *,
    where: str,
    actual: dict[str, Any],
    allowed: tuple[str, ...],
    required: tuple[str, ...] = (),
) -> list[str]:
    errors: list[str] = []
    for key in actual:
        if key not in allowed:
            errors.append(f"{where}: unknown key {key!r}")
    for key in required:
        if key not in actual:
            errors.append(f"{where}: missing required key {key!r}")
    return errors


def validate_runspec_schema(parsed: Any) -> dict[str, Any]:
    """Apply Agent OS RunSpec schema rules to the parsed YAML tree."""
    errors: list[str] = []
    if not isinstance(parsed, dict):
        return {
            "task_count": 0,
            "task_ids": [],
            "errors": ["runspec YAML root must be a mapping"],
        }

    errors.extend(
        _check_keys(
            where="root",
            actual=parsed,
            allowed=ALLOWED_TOP_KEYS,
            required=("apiVersion", "kind", "spec"),
        )
    )

    if parsed.get("kind") != "Run":
        errors.append("runspec root kind must be 'Run'")
    if parsed.get("apiVersion") != "ao.dev/v1":
        errors.append("runspec apiVersion must be 'ao.dev/v1'")

    metadata = parsed.get("metadata")
    if metadata is not None:
        if not isinstance(metadata, dict):
            errors.append("runspec metadata must be a mapping")
        else:
            errors.extend(
                _check_keys(
                    where="metadata",
                    actual=metadata,
                    allowed=ALLOWED_METADATA_KEYS,
                    required=("name",),
                )
            )

    spec = parsed.get("spec")
    if not isinstance(spec, dict):
        errors.append("runspec spec must be a mapping")
        return {
            "task_count": 0,
            "task_ids": [],
            "errors": errors,
        }

    errors.extend(
        _check_keys(
            where="spec",
            actual=spec,
            allowed=ALLOWED_SPEC_KEYS,
            required=("tasks",),
        )
    )

    tasks = spec.get("tasks")
    if not isinstance(tasks, list):
        errors.append("runspec spec.tasks must be a list")
        return {
            "task_count": 0,
            "task_ids": [],
            "errors": errors,
        }

    if not tasks:
        errors.append("runspec spec.tasks must be non-empty")

    task_ids: list[str] = []
    seen_ids: set[str] = set()
    for index, task in enumerate(tasks):
        where = f"task[{index}]"
        if not isinstance(task, dict):
            errors.append(f"{where}: must be a mapping")
            continue
        tid_raw = task.get("id")
        tid = str(tid_raw) if tid_raw is not None else f"<missing#{index}>"
        task_ids.append(tid)
        if tid_raw is None or not isinstance(tid_raw, str) or not tid_raw.strip():
            errors.append(f"{where}: missing or empty id")
        else:
            if tid in seen_ids:
                errors.append(f"duplicate task id: {tid}")
            seen_ids.add(tid)
        errors.extend(
            _check_keys(
                where=f"task {tid}",
                actual=task,
                allowed=ALLOWED_TASK_KEYS,
                required=("id", "kind", "deps", "spec"),
            )
        )
        if task.get("kind") != "agent":
            errors.append(f"task {tid}: kind must be 'agent'")
        deps = task.get("deps")
        if "deps" in task and not isinstance(deps, list):
            errors.append(
                f"task {tid}: deps must be a list (got {type(deps).__name__})"
            )
        elif isinstance(deps, list):
            for dep in deps:
                if not isinstance(dep, str) or not dep.strip():
                    errors.append(f"task {tid}: deps entries must be non-empty strings")
        task_spec = task.get("spec")
        if not isinstance(task_spec, dict):
            errors.append(f"task {tid}: missing or invalid spec block")
            continue
        errors.extend(
            _check_keys(
                where=f"task {tid} spec",
                actual=task_spec,
                allowed=ALLOWED_TASK_SPEC_KEYS,
                required=ALLOWED_TASK_SPEC_KEYS,
            )
        )
        dispatch = task_spec.get("dispatchAuthorized")
        if dispatch is not False:
            errors.append(
                f"task {tid}: dispatchAuthorized must be false (got {dispatch!r})"
            )

    return {
        "task_count": len(tasks),
        "task_ids": task_ids,
        "errors": errors,
    }


def evaluate_runspec_yaml(body: str) -> dict[str, Any]:
    parsed, parse_errors = parse_runspec_yaml(body)
    summary = validate_runspec_schema(parsed)
    errors = list(parse_errors) + list(summary["errors"])
    return {
        "verdict": "PASS" if not errors else "FAIL",
        "task_count": summary["task_count"],
        "task_ids": summary["task_ids"],
        "parse_error_count": len(parse_errors),
        "schema_error_count": len(summary["errors"]),
        "errors": errors,
    }


MUTATION_CASE_IDS = (
    "malformed_yaml_refused",
    "duplicate_task_ids_refused",
    "missing_spec_block_refused",
    "bad_deps_type_refused",
    "unknown_task_field_refused",
    "unsafe_dispatch_authorized_refused",
)


def _first_task_block(body: str) -> tuple[int, int]:
    """Return (start_idx, end_idx) of the first task block.

    Block boundaries are computed by indent: the block starts at the line that
    begins with `    - id:` and ends just before the next line at the same or
    lower indent that starts a new sibling task or unwinds to ancestor scope.
    """
    lines = body.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if line.startswith("    - id:"):
            start = i
            break
    if start is None:
        return (-1, -1)
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("    - id:"):
            end = j
            break
        if lines[j] and not lines[j].startswith(" ") and lines[j].strip():
            end = j
            break
    return (start, end)


def mutate_yaml_body(body: str, case_id: str) -> str:
    """Return a byte-mutated copy of the canonical YAML body for a case."""
    if case_id == "malformed_yaml_refused":
        return body.replace(
            "  name: agent-os-phase-draft",
            '  name: "agent-os-phase-draft',
            1,
        )
    if case_id == "duplicate_task_ids_refused":
        start, end = _first_task_block(body)
        if start < 0:
            return body
        lines = body.splitlines(keepends=True)
        block = "".join(lines[start:end])
        return "".join(lines[:end]) + block + "".join(lines[end:])
    if case_id == "missing_spec_block_refused":
        start, end = _first_task_block(body)
        if start < 0:
            return body
        lines = body.splitlines(keepends=True)
        kept: list[str] = []
        skip_spec = False
        for idx in range(start, end):
            line = lines[idx]
            if not skip_spec and line.startswith("      spec:"):
                skip_spec = True
                continue
            if skip_spec:
                if line.startswith("        "):
                    continue
                skip_spec = False
            kept.append(line)
        return "".join(lines[:start]) + "".join(kept) + "".join(lines[end:])
    if case_id == "bad_deps_type_refused":
        return body.replace(
            'deps: ["agent-os-planner"]',
            "deps: agent-os-planner",
            1,
        )
    if case_id == "unknown_task_field_refused":
        return body.replace(
            "      kind: agent\n",
            "      kind: agent\n      mysteryField: enabled\n",
            1,
        )
    if case_id == "unsafe_dispatch_authorized_refused":
        return body.replace(
            "        dispatchAuthorized: false",
            "        dispatchAuthorized: true",
            1,
        )
    return body


def mutation_cases(body: str) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for case_id in MUTATION_CASE_IDS:
        mutated = mutate_yaml_body(body, case_id)
        evaluation = evaluate_runspec_yaml(mutated)
        cases.append(
            {
                "id": case_id,
                "observed_verdict": evaluation["verdict"],
                "error_count": len(evaluation["errors"]),
                "parse_error_count": evaluation["parse_error_count"],
                "schema_error_count": evaluation["schema_error_count"],
                "dispatch_authorized": False,
                "live_providers_run": False,
            }
        )
    return cases


def build_report(
    *,
    root: Path = ROOT,
    runspec: str | Path = DEFAULT_RUNSPEC,
) -> dict[str, Any]:
    root = root.resolve()
    runspec_path = resolve_path(root, runspec)
    try:
        body = runspec_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        body = ""
        baseline_errors = [f"runspec YAML missing: {relpath(root, runspec_path)}"]
        baseline = {
            "verdict": "FAIL",
            "task_count": 0,
            "task_ids": [],
            "parse_error_count": 0,
            "schema_error_count": len(baseline_errors),
            "errors": baseline_errors,
        }
        cases: list[dict[str, Any]] = []
    else:
        baseline = evaluate_runspec_yaml(body)
        cases = mutation_cases(body)

    errors = list(baseline["errors"])
    for case in cases:
        if case["observed_verdict"] != "FAIL":
            errors.append(f"{case['id']} must fail closed")
        if case["dispatch_authorized"] or case["live_providers_run"]:
            errors.append(f"{case['id']} must keep dispatch/live flags false")

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "runspec_path": relpath(root, runspec_path),
        "task_count": baseline["task_count"],
        "task_ids": baseline["task_ids"],
        "baseline_errors": baseline["errors"],
        "mutation_case_count": len(cases),
        "mutation_cases": cases,
        "mutation_case_ids": list(MUTATION_CASE_IDS),
        "allowed_top_keys": list(ALLOWED_TOP_KEYS),
        "allowed_task_keys": list(ALLOWED_TASK_KEYS),
        "allowed_task_spec_keys": list(ALLOWED_TASK_SPEC_KEYS),
        "errors": errors,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_safe_command": (
            "RunSpec YAML schema/format injection passes; continue Agent OS architecture implementation behind no-provider gates."
            if not errors
            else "Fix RunSpec YAML schema/format failures before changing role graph, router, or RunSpec generation."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check Agent OS RunSpec YAML schema/format failure injection"
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--runspec", default=DEFAULT_RUNSPEC)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = build_report(root=args.root, runspec=args.runspec)
    if args.write_output is not None:
        output = resolve_path(args.root, args.write_output)
        write_json(output, payload)
        payload["output"] = relpath(args.root.resolve(), output.resolve())
    print(
        json.dumps(payload, indent=2, sort_keys=True)
        if args.json
        else f"verdict={payload['verdict']}"
    )
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
