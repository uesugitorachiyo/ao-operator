#!/usr/bin/env python3
"""Check AO Operator public-release security posture.

The default surface is CI-safe: source, public docs, examples, workflows, and
agent contracts. Use --strict-public to include committed status/evidence
artifacts before publishing the repository as a public artifact.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ao-operator/public-release-security/v1"

DEFAULT_PREFIXES = (
    ".github/",
    "agents/",
    "ao/",
    "docs/",
    "examples/",
    "scripts/",
    "skills/",
    "README.md",
    "SECURITY.md",
    "SETUP.md",
    "PROMPT_SAMPLES.md",
    "ao-operator.md",
)
DEFAULT_EXCLUDED_PREFIXES = (
    "run-artifacts/",
    "docs/evaluations/",
)
TEXT_SUFFIXES = {
    ".cfg",
    ".env",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
PYTHON_SUFFIXES = {".py"}

TEXT_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "text.private_key",
        "HIGH",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ),
    (
        "text.api_key_assignment",
        "HIGH",
        re.compile(r"(?i)\b(?:OPENAI_API_KEY|ANTHROPIC_API_KEY)\s*=\s*[^`'\"]\S+"),
    ),
    (
        "text.token_shape",
        "HIGH",
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    ),
    (
        "text.stale_context",
        "MEDIUM",
        re.compile(r"<claude-mem-context>|FACTORY_V3_LLM_WIKI_PATH|path:llm_wiki"),
    ),
    (
        "text.personal_path",
        "MEDIUM",
        re.compile(r"(?<!\[REDACTED_USER\])(?:/Users/[^\s`\"'\\]+|/home/(?!\[REDACTED_USER\])[^\s`\"'\\]+|/opt/ai-workstation/[^\s`\"'\\]+)"),
    ),
    (
        "text.private_network_target",
        "MEDIUM",
        re.compile(r"(?:\b\w+@)?(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})"),
    ),
)

SHELL_TAR_RE = re.compile(r"\btar\s+-(?:[A-Za-z]*x[A-Za-z]*|x[A-Za-z]*)")

CERT_ALIGNMENT = {
    "ast.subprocess_shell_true": [
        "SEI CERT secure coding: command construction must avoid shell interpretation where structured APIs can be used.",
        "Python subprocess security guidance: pass argv lists and keep shell=False unless a documented exception is reviewed.",
    ],
    "ast.shell_tar_extract": [
        "SEI CERT secure coding: validate untrusted input before file-system writes.",
        "Archive extraction must enforce path, link, special-file, entry-count, and size constraints.",
    ],
    "ast.tarfile_extract": [
        "SEI CERT secure coding: validate untrusted input before file-system writes.",
        "Archive extraction must avoid bulk extract/extractall without member validation.",
    ],
    "ast.ssh_accept_new": [
        "SEI CERT secure coding: authenticate remote endpoints before exchanging artifacts.",
        "Remote DAST and smoke tests must use pinned host identity, not opportunistic trust.",
    ],
    "text.api_key_assignment": [
        "SEI CERT secure coding: do not expose credentials in source, docs, or generated artifacts.",
    ],
    "text.private_key": [
        "SEI CERT secure coding: do not expose private keys in source, docs, or generated artifacts.",
    ],
    "text.token_shape": [
        "SEI CERT secure coding: do not expose bearer tokens in source, docs, or generated artifacts.",
    ],
    "text.personal_path": [
        "Public-release hygiene: replace operator-local paths with templates or redacted placeholders.",
    ],
    "text.private_network_target": [
        "Public-release hygiene: replace lab network targets with environment variables or placeholders.",
    ],
    "text.stale_context": [
        "Public-release hygiene: remove disconnected context-injection markers from shipped surfaces.",
    ],
    "ast.syntax_error": [
        "Static-analysis hygiene: keep Python parseable so AST controls can run.",
    ],
}

REMEDIATION_ACTIONS = {
    "ast.subprocess_shell_true": "Replace shell=True with an argv-list subprocess call or add a reviewed exception outside the public-release surface.",
    "ast.shell_tar_extract": "Replace shell tar extraction with safe member-by-member extraction.",
    "ast.tarfile_extract": "Replace tarfile extract/extractall with validation for traversal, links, special files, count, and total size.",
    "ast.ssh_accept_new": "Require StrictHostKeyChecking=yes and a pre-pinned known_hosts entry.",
    "text.api_key_assignment": "Remove the assignment or rewrite it as a non-value policy example.",
    "text.private_key": "Remove the key material and rotate the affected key before release.",
    "text.token_shape": "Remove the token-shaped value and rotate it if it was ever live.",
    "text.personal_path": "Replace personal or lab paths with ${FACTORY_V3_*} examples or [REDACTED_*] placeholders.",
    "text.private_network_target": "Replace private IPs and host aliases with ${FACTORY_V3_REMOTE_HOST} examples.",
    "text.stale_context": "Delete stale context-injection markers and document standalone lookup paths without active config names.",
    "ast.syntax_error": "Fix Python syntax so AST scanning can cover the file.",
}


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def add_finding(
    findings: list[dict[str, Any]],
    *,
    finding_id: str,
    severity: str,
    path: Path,
    root: Path,
    line: int,
    message: str,
) -> None:
    findings.append(
        {
            "id": finding_id,
            "severity": severity,
            "path": relpath(root, path),
            "line": line,
            "message": message,
        }
    )


def is_self_detection_literal(root: Path, path: Path, finding_id: str) -> bool:
    return relpath(root, path) == "scripts/check_public_release_security.py" and finding_id in {
        "text.private_key",
        "text.api_key_assignment",
        "text.token_shape",
        "text.stale_context",
        "text.personal_path",
        "text.private_network_target",
        "ast.ssh_accept_new",
        "ast.shell_tar_extract",
    }


def is_candidate(rel: str, *, include_status: bool) -> bool:
    if not rel or rel.startswith(".git/"):
        return False
    if not include_status and rel.startswith(DEFAULT_EXCLUDED_PREFIXES):
        return False
    return rel.startswith(DEFAULT_PREFIXES)


def tracked_files(root: Path, *, include_status: bool = False) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode == 0:
        rels = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return [
            root / rel
            for rel in rels
            if is_candidate(rel, include_status=include_status)
            and (root / rel).suffix in TEXT_SUFFIXES
        ]
    return [
        path
        for path in root.rglob("*")
        if path.is_file()
        and is_candidate(relpath(root, path), include_status=include_status)
        and path.suffix in TEXT_SUFFIXES
    ]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def source_line(text: str, line: int) -> str:
    lines = text.splitlines()
    if 1 <= line <= len(lines):
        return lines[line - 1]
    return ""


def is_detection_regex_literal(text: str, line: int) -> bool:
    value = source_line(text, line)
    return "re.compile(" in value and ("r\"" in value or "r'" in value)


def scan_text(root: Path, path: Path, findings: list[dict[str, Any]]) -> None:
    body = read_text(path)
    for finding_id, severity, pattern in TEXT_PATTERNS:
        for match in pattern.finditer(body):
            line = line_for_offset(body, match.start())
            if path.suffix == ".py" and finding_id == "text.stale_context":
                continue
            if is_self_detection_literal(root, path, finding_id):
                continue
            if is_detection_regex_literal(body, line):
                continue
            add_finding(
                findings,
                finding_id=finding_id,
                severity=severity,
                path=path,
                root=root,
                line=line,
                message=f"{finding_id} marker must not ship in public release surface",
            )


def full_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = full_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def keyword_is_true(call: ast.Call, name: str) -> bool:
    for keyword in call.keywords:
        if keyword.arg == name and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
            return True
    return False


def scan_python_ast(root: Path, path: Path, findings: list[dict[str, Any]]) -> None:
    try:
        tree = ast.parse(read_text(path), filename=str(path))
    except SyntaxError as exc:
        add_finding(
            findings,
            finding_id="ast.syntax_error",
            severity="LOW",
            path=path,
            root=root,
            line=exc.lineno or 1,
            message="Python file could not be parsed for security AST checks",
        )
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = full_name(node.func)
            if name in {
                "subprocess.run",
                "subprocess.Popen",
                "subprocess.call",
                "subprocess.check_call",
                "subprocess.check_output",
            } and keyword_is_true(node, "shell"):
                add_finding(
                    findings,
                    finding_id="ast.subprocess_shell_true",
                    severity="HIGH",
                    path=path,
                    root=root,
                    line=getattr(node, "lineno", 1),
                    message="subprocess shell=True requires a structured-command replacement or explicit security exception",
                )
            if isinstance(node.func, ast.Attribute) and node.func.attr in {"extract", "extractall"}:
                add_finding(
                    findings,
                    finding_id="ast.tarfile_extract",
                    severity="HIGH",
                    path=path,
                    root=root,
                    line=getattr(node, "lineno", 1),
                    message="tarfile extract/extractall must be replaced with member-by-member safe extraction",
                )
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            line = getattr(node, "lineno", 1)
            if "StrictHostKeyChecking=accept-new" in value:
                if not is_self_detection_literal(root, path, "ast.ssh_accept_new"):
                    add_finding(
                        findings,
                        finding_id="ast.ssh_accept_new",
                        severity="MEDIUM",
                        path=path,
                        root=root,
                        line=line,
                        message="public remote smoke must pin host keys instead of accept-new",
                    )
            if SHELL_TAR_RE.search(value):
                if not is_self_detection_literal(root, path, "ast.shell_tar_extract"):
                    add_finding(
                        findings,
                        finding_id="ast.shell_tar_extract",
                        severity="HIGH",
                        path=path,
                        root=root,
                        line=line,
                        message="shell tar extraction must be replaced with validated safe extraction",
                    )


SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


def build_finding_groups(findings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for item in findings:
        group = groups.setdefault(
            item["id"],
            {
                "id": item["id"],
                "severity": item["severity"],
                "count": 0,
                "paths": {},
                "cert_alignment": CERT_ALIGNMENT.get(item["id"], []),
                "next_action": REMEDIATION_ACTIONS.get(item["id"], "Review and remediate this finding before public release."),
            },
        )
        group["count"] += 1
        group["paths"][item["path"]] = group["paths"].get(item["path"], 0) + 1

    for group in groups.values():
        group["paths"] = dict(sorted(group["paths"].items(), key=lambda pair: (-pair[1], pair[0]))[:20])
    return dict(
        sorted(
            groups.items(),
            key=lambda pair: (-SEVERITY_RANK[pair[1]["severity"]], -pair[1]["count"], pair[0]),
        )
    )


def build_remediation_plan(groups: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "finding_id": group["id"],
            "severity": group["severity"],
            "count": group["count"],
            "next_action": group["next_action"],
            "top_paths": group["paths"],
            "cert_alignment": group["cert_alignment"],
        }
        for group in groups.values()
    ]


def scan_paths(root: Path, paths: Iterable[Path], *, fail_on: str = "LOW") -> dict[str, Any]:
    root = root.resolve()
    findings: list[dict[str, Any]] = []
    scanned = 0
    ast_scanned = 0
    for raw_path in paths:
        path = raw_path if raw_path.is_absolute() else root / raw_path
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        scanned += 1
        scan_text(root, path, findings)
        if path.suffix in PYTHON_SUFFIXES:
            ast_scanned += 1
            scan_python_ast(root, path, findings)

    findings.sort(key=lambda item: (item["severity"], item["path"], item["line"], item["id"]))
    high = sum(1 for item in findings if item["severity"] == "HIGH")
    medium = sum(1 for item in findings if item["severity"] == "MEDIUM")
    low = sum(1 for item in findings if item["severity"] == "LOW")
    threshold = SEVERITY_RANK[fail_on]
    blocking = [item for item in findings if SEVERITY_RANK[item["severity"]] >= threshold]
    groups = build_finding_groups(findings)
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if not blocking else "FAIL",
        "files_checked": scanned,
        "python_ast_files_checked": ast_scanned,
        "fail_on": fail_on,
        "blocking_findings": len(blocking),
        "summary": {
            "HIGH": high,
            "MEDIUM": medium,
            "LOW": low,
            "total": len(findings),
        },
        "finding_groups": groups,
        "remediation_plan": build_remediation_plan(groups),
        "findings": findings,
        "dispatch_authorized": False,
        "live_providers_run": False,
    }


def resolve_paths(root: Path, values: list[str], *, include_status: bool) -> list[Path]:
    if values:
        return [Path(value) if Path(value).is_absolute() else root / value for value in values]
    return tracked_files(root, include_status=include_status)


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def summary_only_payload(payload: dict[str, Any], *, sample_size: int = 20) -> dict[str, Any]:
    compact = dict(payload)
    findings = list(compact.pop("findings", []))
    compact["findings_sample"] = findings[:sample_size]
    compact["findings_omitted"] = len(findings)
    return compact


def text_report(payload: dict[str, Any]) -> str:
    findings = list(payload.get("findings", payload.get("findings_sample", [])))
    lines = [
        f"verdict={payload['verdict']}",
        f"files_checked={payload['files_checked']}",
        f"python_ast_files_checked={payload['python_ast_files_checked']}",
        "findings={total} high={HIGH} medium={MEDIUM} low={LOW}".format(**payload["summary"]),
    ]
    for item in findings[:20]:
        lines.append(f"{item['severity']} {item['id']} {item['path']}:{item['line']} {item['message']}")
    remaining = max(payload.get("findings_omitted", len(findings)) - len(findings[:20]), 0)
    if remaining > 0:
        lines.append(f"... {remaining} more finding(s)")
    if payload.get("remediation_plan"):
        lines.append("remediation_plan:")
        for item in payload["remediation_plan"][:10]:
            lines.append(f"- {item['severity']} {item['finding_id']} count={item['count']} action={item['next_action']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check public-release security posture")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--path", action="append", default=[], help="Path to scan; may be repeated")
    parser.add_argument("--include-status", action="store_true", help="Include run-artifacts and docs/evaluations")
    parser.add_argument("--strict-public", action="store_true", help="Alias for --include-status")
    parser.add_argument("--fail-on", choices=["LOW", "MEDIUM", "HIGH"], default="LOW")
    parser.add_argument("--write-output", type=Path)
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Omit the full findings list from stdout and written JSON; keep summary, groups, remediation, and a small sample",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    include_status = args.include_status or args.strict_public
    payload = scan_paths(root, resolve_paths(root, args.path, include_status=include_status), fail_on=args.fail_on)
    payload["mode"] = "strict-public" if include_status else "public-surface"
    if args.summary_only:
        payload = summary_only_payload(payload)
    if args.write_output:
        output = args.write_output if args.write_output.is_absolute() else root / args.write_output
        write_output(output, payload)
        payload["output"] = str(output)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else text_report(payload))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
