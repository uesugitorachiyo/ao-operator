#!/usr/bin/env python3
"""Deterministic AO2 obligation ledger extraction and checking."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "ao2.obligation-ledger.v1"
TEXT_EXTENSIONS = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".py",
    ".rs",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
SKIP_DIRS = {".git", ".ao2", "node_modules", "target", "__pycache__"}
GENERATED_EVIDENCE_DIR_PARTS = {
    ("docs", "status"),
    ("docs", "evaluations"),
    ("run-artifacts",),
}


def extract_ledger(source: Path, source_path: str | None = None) -> dict[str, Any]:
    text = source.read_text(encoding="utf-8")
    display_path = source_path or source.as_posix()
    obligations = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        statement = _clean_statement(raw_line)
        if not statement or not _is_obligation(statement):
            continue
        obligations.append(
            {
                "id": f"OBL-{len(obligations) + 1:03}",
                "kind": _kind(statement),
                "statement": statement,
                "source_path": display_path,
                "source_line": line_number,
                "source_excerpt_hash": "sha256:" + _sha256(statement.encode("utf-8")),
                "expected_fragments": _expected_fragments(statement),
                "status": "unverified",
                "evidence": [],
                "waiver": None,
            }
        )
    ledger = {
        "schema_version": SCHEMA_VERSION,
        "source_contracts": [
            {
                "path": display_path,
                "sha256": "sha256:" + _sha256(text.encode("utf-8")),
            }
        ],
        "obligations": obligations,
        "summary": {"pass": 0, "fail": 0, "unverified": 0, "waived": 0},
        "verdict": "rejected",
        "created_at": _now(),
    }
    return _refresh(ledger)


def check_ledger(ledger: dict[str, Any], target_root: Path) -> dict[str, Any]:
    checked = dict(ledger)
    checked["source_contracts"] = list(ledger.get("source_contracts") or [])
    checked["obligations"] = [dict(item) for item in ledger.get("obligations") or []]
    source_paths = {
        str(item.get("path", "")).replace("\\", "/")
        for item in checked["source_contracts"]
        if isinstance(item, dict)
    }
    files = list(_searchable_files(target_root, source_paths))
    for obligation in checked["obligations"]:
        obligation["evidence"] = []
        if obligation.get("waiver"):
            obligation["status"] = "waived"
            continue
        fragments = [
            str(fragment)
            for fragment in obligation.get("expected_fragments", [])
            if str(fragment).strip()
        ]
        if not fragments:
            obligation["status"] = "unverified"
            continue
        evidence = []
        for fragment in fragments:
            found = _find_fragment(target_root, files, fragment)
            if found is not None:
                evidence.append(found)
        if len(evidence) == len(fragments):
            obligation["status"] = "pass"
            obligation["evidence"] = evidence
        else:
            obligation["status"] = "fail"
    checked["created_at"] = _now()
    return _refresh(checked)


def exact_fragment_ledger(ledger: dict[str, Any]) -> dict[str, Any]:
    """Return a ledger containing only obligations with deterministic fragments."""
    filtered = dict(ledger)
    obligations = []
    for obligation in ledger.get("obligations") or []:
        if obligation.get("expected_fragments"):
            item = dict(obligation)
            item["id"] = f"OBL-{len(obligations) + 1:03}"
            obligations.append(item)
    filtered["source_contracts"] = list(ledger.get("source_contracts") or [])
    filtered["obligations"] = obligations
    filtered["created_at"] = _now()
    return _refresh(filtered)


def write_ledger(path: Path, ledger: dict[str, Any]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _clean_statement(raw_line: str) -> str:
    text = raw_line.strip().lstrip("-*").strip()
    while text and (text[0].isdigit() or text[0] == "."):
        text = text[1:].strip()
    return text


def _is_obligation(statement: str) -> bool:
    lower = statement.lower()
    return any(
        marker in lower
        for marker in (
            "must",
            "shall",
            "required",
            "acceptance",
            "rubric",
            "preserve",
            "unchanged",
            "verbatim",
        )
    )


def _kind(statement: str) -> str:
    lower = statement.lower()
    if "must not" in lower or "shall not" in lower or "forbidden" in lower:
        return "must_not"
    if any(marker in lower for marker in ("preserve", "unchanged", "verbatim", "exact", "equation")):
        return "content_preservation"
    if "acceptance" in lower:
        return "acceptance"
    if "rubric" in lower:
        return "rubric"
    return "must"


def _expected_fragments(statement: str) -> list[str]:
    fragments = []
    for delimiter in ("`", "$"):
        fragments.extend(_delimited_fragments(statement, delimiter))
    return sorted({fragment.strip() for fragment in fragments if fragment.strip()})


def _delimited_fragments(statement: str, delimiter: str) -> list[str]:
    fragments: list[str] = []
    current: list[str] = []
    in_fragment = False
    for char in statement:
        if char == delimiter:
            if in_fragment:
                fragments.append("".join(current).strip())
                current = []
                in_fragment = False
            else:
                in_fragment = True
        elif in_fragment:
            current.append(char)
    return fragments


def _searchable_files(root: Path, source_paths: set[str]):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel in source_paths:
            continue
        parts = path.relative_to(root).parts
        if any(part in SKIP_DIRS for part in parts):
            continue
        if any(_has_prefix(parts, prefix) for prefix in GENERATED_EVIDENCE_DIR_PARTS):
            continue
        if path.stat().st_size > 2_000_000:
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        yield path


def _has_prefix(parts: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
    return len(parts) >= len(prefix) and tuple(parts[: len(prefix)]) == prefix


def _find_fragment(root: Path, files: list[Path], fragment: str) -> dict[str, Any] | None:
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if fragment in line:
                return {
                    "path": path.relative_to(root).as_posix(),
                    "line": line_number,
                    "detail": f"found expected fragment `{fragment}`",
                }
    return None


def _refresh(ledger: dict[str, Any]) -> dict[str, Any]:
    summary = {"pass": 0, "fail": 0, "unverified": 0, "waived": 0}
    for obligation in ledger.get("obligations") or []:
        status = obligation.get("status")
        if status in summary:
            summary[status] += 1
    ledger["summary"] = summary
    ledger["verdict"] = "accepted" if summary["fail"] == 0 and summary["unverified"] == 0 else "rejected"
    return ledger


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
