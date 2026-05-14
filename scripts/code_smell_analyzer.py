#!/usr/bin/env python3
"""Conservative, stdlib-only Python code-smell analyzer.

The analyzer is intended as pre-refactor evidence, not as a quality gate. It
reports stable JSON/text findings for long files, long functions, branch-heavy
functions, broad exception handlers, and repeated function names across files.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
import tempfile
import textwrap
from typing import Iterable


DEFAULT_EXCLUDES = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
    "venv",
}
COMMON_DUPLICATE_NAMES = {
    "main",
    "run",
    "parse_args",
    "test",
    "setup",
    "teardown",
}
BRANCH_NODES = tuple(
    node
    for node in (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.ExceptHandler,
    ast.With,
    ast.AsyncWith,
    ast.BoolOp,
    ast.IfExp,
    getattr(ast, "Match", None),
)
    if node is not None
)


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    path: str
    message: str
    line: int | None = None
    symbol: str | None = None
    metric: int | None = None
    threshold: int | None = None


def _rel(path: Path, root: Path) -> str:
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        rel = path.resolve()
    return rel.as_posix()


def discover_python_files(paths: Iterable[Path], *, root: Path) -> list[Path]:
    files: set[Path] = set()
    for path in paths:
        path = path.resolve()
        if path.is_file() and path.suffix == ".py":
            if not _is_excluded(path, root=root):
                files.add(path)
            continue
        if path.is_dir():
            for candidate in path.rglob("*.py"):
                if not _is_excluded(candidate, root=root):
                    files.add(candidate.resolve())
    return sorted(files, key=lambda item: _rel(item, root))


def _is_excluded(path: Path, *, root: Path) -> bool:
    try:
        parts = path.resolve().relative_to(root.resolve()).parts
    except ValueError:
        parts = path.resolve().parts
    return any(part in DEFAULT_EXCLUDES for part in parts)


def analyze_files(
    files: Iterable[Path],
    *,
    root: Path,
    long_file_lines: int,
    long_function_lines: int,
    branch_threshold: int,
    duplicate_name_threshold: int,
) -> dict:
    findings: list[Finding] = []
    functions_by_name: dict[str, list[tuple[Path, int]]] = {}
    files_seen = 0

    for path in files:
        files_seen += 1
        file_findings, file_functions = _analyze_file(
            path,
            root=root,
            long_file_lines=long_file_lines,
            long_function_lines=long_function_lines,
            branch_threshold=branch_threshold,
        )
        findings.extend(file_findings)
        for name, locations in file_functions.items():
            functions_by_name.setdefault(name, []).extend(locations)

    findings.extend(
        _duplicate_name_findings(
            functions_by_name,
            root=root,
            duplicate_name_threshold=duplicate_name_threshold,
        )
    )
    serializable = [asdict(finding) for finding in sorted(findings, key=_finding_sort_key)]
    return {
        "verdict": "WARN" if serializable else "PASS",
        "files_analyzed": files_seen,
        "summary": _summary(serializable),
        "findings": serializable,
    }


def _analyze_file(
    path: Path,
    *,
    root: Path,
    long_file_lines: int,
    long_function_lines: int,
    branch_threshold: int,
) -> tuple[list[Finding], dict[str, list[tuple[Path, int]]]]:
    rel_path = _rel(path, root)
    text = _read_python(path)
    findings = _file_size_findings(
        rel_path,
        text=text,
        long_file_lines=long_file_lines,
    )
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        findings.append(
            Finding(
                code="syntax-error",
                severity="high",
                path=rel_path,
                line=exc.lineno,
                message=exc.msg,
            )
        )
        return findings, {}
    node_findings, functions = _tree_findings(
        tree,
        path=path,
        rel_path=rel_path,
        long_function_lines=long_function_lines,
        branch_threshold=branch_threshold,
    )
    findings.extend(node_findings)
    return findings, functions


def _read_python(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _file_size_findings(
    rel_path: str,
    *,
    text: str,
    long_file_lines: int,
) -> list[Finding]:
    line_count = text.count("\n") + (1 if text else 0)
    if line_count <= long_file_lines:
        return []
    return [
        Finding(
            code="long-file",
            severity="medium",
            path=rel_path,
            line=1,
            message=f"file has {line_count} lines",
            metric=line_count,
            threshold=long_file_lines,
        )
    ]


def _tree_findings(
    tree: ast.AST,
    *,
    path: Path,
    rel_path: str,
    long_function_lines: int,
    branch_threshold: int,
) -> tuple[list[Finding], dict[str, list[tuple[Path, int]]]]:
    findings: list[Finding] = []
    functions: dict[str, list[tuple[Path, int]]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.setdefault(node.name, []).append((path, node.lineno))
            findings.extend(
                _function_findings(
                    node,
                    rel_path=rel_path,
                    long_function_lines=long_function_lines,
                    branch_threshold=branch_threshold,
                )
            )
        if isinstance(node, ast.ExceptHandler) and _is_broad_exception(node):
            findings.append(
                Finding(
                    code="broad-except",
                    severity="low",
                    path=rel_path,
                    line=node.lineno,
                    message="broad exception handler",
                )
            )
    return findings, functions


def _function_findings(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    rel_path: str,
    long_function_lines: int,
    branch_threshold: int,
) -> list[Finding]:
    findings: list[Finding] = []
    line_span = _node_line_span(node)
    branch_count = _branch_count(node)
    if line_span > long_function_lines:
        findings.append(
            Finding(
                code="long-function",
                severity="medium",
                path=rel_path,
                line=node.lineno,
                symbol=node.name,
                message=f"function has {line_span} lines",
                metric=line_span,
                threshold=long_function_lines,
            )
        )
    if branch_count > branch_threshold:
        findings.append(
            Finding(
                code="branch-heavy-function",
                severity="medium",
                path=rel_path,
                line=node.lineno,
                symbol=node.name,
                message=f"function has {branch_count} branch/decision nodes",
                metric=branch_count,
                threshold=branch_threshold,
            )
        )
    return findings


def _node_line_span(node: ast.AST) -> int:
    lineno = getattr(node, "lineno", 0) or 0
    end_lineno = getattr(node, "end_lineno", lineno) or lineno
    return max(1, end_lineno - lineno + 1)


def _branch_count(node: ast.AST) -> int:
    count = 0
    for child in ast.walk(node):
        if child is node:
            continue
        if isinstance(child, BRANCH_NODES):
            count += 1
    return count


def _is_broad_exception(node: ast.ExceptHandler) -> bool:
    if node.type is None:
        return True
    if isinstance(node.type, ast.Name):
        return node.type.id in {"Exception", "BaseException"}
    if isinstance(node.type, ast.Tuple):
        return any(isinstance(elt, ast.Name) and elt.id == "Exception" for elt in node.type.elts)
    return False


def _duplicate_name_findings(
    functions_by_name: dict[str, list[tuple[Path, int]]],
    *,
    root: Path,
    duplicate_name_threshold: int,
) -> list[Finding]:
    findings: list[Finding] = []
    for name, locations in sorted(functions_by_name.items()):
        if name.startswith("__") and name.endswith("__"):
            continue
        if name in COMMON_DUPLICATE_NAMES or len(name) <= 3:
            continue
        unique_files = {_rel(path, root) for path, _line in locations}
        if len(unique_files) < duplicate_name_threshold:
            continue
        files = ", ".join(sorted(unique_files)[:6])
        findings.append(
            Finding(
                code="duplicate-function-name",
                severity="info",
                path=sorted(unique_files)[0],
                symbol=name,
                message=f"function name appears in {len(unique_files)} files: {files}",
                metric=len(unique_files),
                threshold=duplicate_name_threshold,
            )
        )
    return findings


def _summary(findings: list[dict]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for finding in findings:
        code = str(finding["code"])
        summary[code] = summary.get(code, 0) + 1
    return dict(sorted(summary.items()))


def _finding_sort_key(finding: Finding) -> tuple[str, int, str]:
    return (finding.path, finding.line or 0, finding.code)


def render_text(result: dict) -> str:
    lines = [
        f"verdict: {result['verdict']}",
        f"files_analyzed: {result['files_analyzed']}",
    ]
    if not result["findings"]:
        lines.append("findings: none")
        return "\n".join(lines)
    lines.append("findings:")
    for finding in result["findings"]:
        location = finding["path"]
        if finding.get("line"):
            location += f":{finding['line']}"
        symbol = f" {finding['symbol']}" if finding.get("symbol") else ""
        lines.append(f"- {finding['severity']} {finding['code']} {location}{symbol}: {finding['message']}")
    return "\n".join(lines)


def self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = root / "pkg"
        package.mkdir()
        repeated = "def shared_helper():\n    return 1\n"
        for index in range(3):
            (package / f"mod{index}.py").write_text(repeated, encoding="utf-8")
        (package / "complex.py").write_text(
            textwrap.dedent(
                """
                def risky(value):
                    try:
                        if value:
                            return 1
                        return 0
                    except Exception:
                        return -1
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        result = analyze_files(
            discover_python_files([package], root=root),
            root=root,
            long_file_lines=20,
            long_function_lines=4,
            branch_threshold=1,
            duplicate_name_threshold=3,
        )
        codes = {finding["code"] for finding in result["findings"]}
        expected = {"broad-except", "branch-heavy-function", "long-function", "duplicate-function-name"}
        if result["verdict"] != "WARN" or not expected <= codes:
            print(json.dumps(result, indent=2, sort_keys=True), file=sys.stderr)
            return 1
    print("OK code_smell_analyzer self-test")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze Python code-smell signals.")
    parser.add_argument("paths", nargs="*", type=Path, help="files or directories to analyze")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="repo root for relative paths")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--long-file-lines", type=int, default=800)
    parser.add_argument("--long-function-lines", type=int, default=80)
    parser.add_argument("--branch-threshold", type=int, default=12)
    parser.add_argument("--duplicate-name-threshold", type=int, default=3)
    parser.add_argument("--self-test", action="store_true", help="run built-in self-test")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.self_test:
        return self_test()
    root = args.repo.resolve()
    paths = args.paths or [root]
    files = discover_python_files(paths, root=root)
    result = analyze_files(
        files,
        root=root,
        long_file_lines=args.long_file_lines,
        long_function_lines=args.long_function_lines,
        branch_threshold=args.branch_threshold,
        duplicate_name_threshold=args.duplicate_name_threshold,
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(render_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
