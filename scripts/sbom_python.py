#!/usr/bin/env python3
"""Generate the Python-side SBOM for AO Operator.

Reads ``requirements-dev.txt`` to discover direct dev dependencies, then
uses :mod:`importlib.metadata` (stdlib) to enumerate installed versions,
licenses, and OSI classifiers for both direct and transitive dependencies.

The default production path under ``scripts/`` is stdlib-only; optional
production features are lazy and listed separately from required runtime
dependencies. See ``docs/sbom/README.md``.

Usage::

    python3 scripts/sbom_python.py > docs/sbom/python-deps.json
"""

from __future__ import annotations

import datetime
import importlib.metadata as md
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_DEV = REPO_ROOT / "requirements-dev.txt"

OPTIONAL_PRODUCTION_DEPENDENCIES = [
    {
        "name": "cryptography",
        "kind": "python-package",
        "required": False,
        "used_for": "Ed25519 evidence-pack signing and verification",
        "activation": "--ed25519-private-key or --evidence-ed25519-private-key",
        "supply_chain_note": "Lazy import only; not required for default HMAC/dev evidence packs.",
    },
    {
        "name": "zstd CLI",
        "kind": "system-binary",
        "required": False,
        "used_for": "Production evidence-pack .tar.zst archive compression and replay",
        "activation": "--tar-zst or live-run evidence-pack archive generation",
        "supply_chain_note": "Resolved with shutil.which('zstd'); not vendored or imported as a Python package.",
    },
]

_PKG_LINE = re.compile(r"^([A-Za-z0-9_.\-]+)")


def _direct_dev_packages() -> list[str]:
    if not REQUIREMENTS_DEV.exists():
        return []
    names: list[str] = []
    for raw in REQUIREMENTS_DEV.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _PKG_LINE.match(line)
        if m:
            names.append(m.group(1))
    return names


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _classifier_short(classifiers: list[str]) -> str:
    for c in classifiers:
        if c.startswith("License ::"):
            return c.split("::")[-1].strip()
    return ""


def _describe(name: str, kind: str) -> dict | None:
    try:
        dist = md.distribution(name)
    except md.PackageNotFoundError:
        return None
    meta = dist.metadata
    return {
        "name": meta["Name"],
        "version": dist.version,
        "license": meta.get("License") or meta.get("License-Expression") or "",
        "classifier": _classifier_short(list(meta.get_all("Classifier") or [])),
        "summary": meta.get("Summary") or "",
        "kind": kind,
    }


def _requirement_is_active(req: str) -> bool:
    """Return True if the requirement applies in the current environment.

    Skips conditional extras like ``pytest[test]`` and markers that gate
    optional features (``; extra == 'docs'``) so the SBOM only lists what
    is actually loadable at runtime.
    """
    if ";" not in req:
        return True
    _, marker = req.split(";", 1)
    marker = marker.strip()
    try:
        from packaging.markers import Marker  # type: ignore

        return Marker(marker).evaluate()
    except Exception:
        # Conservative: if we cannot evaluate, treat as inactive.
        return False


def _transitive(direct: list[str]) -> list[str]:
    seen: set[str] = {_canonical(n) for n in direct}
    queue = list(direct)
    found: list[str] = []
    while queue:
        name = queue.pop(0)
        try:
            dist = md.distribution(name)
        except md.PackageNotFoundError:
            continue
        for req in dist.requires or []:
            if not _requirement_is_active(req):
                continue
            req_name = _PKG_LINE.match(req)
            if not req_name:
                continue
            child = req_name.group(1)
            if _canonical(child) in seen:
                continue
            seen.add(_canonical(child))
            try:
                md.distribution(child)
            except md.PackageNotFoundError:
                continue
            found.append(child)
            queue.append(child)
    return found


def build_sbom() -> dict:
    direct = _direct_dev_packages()
    transitive = _transitive(direct)
    dev: list[dict] = []
    for n in direct:
        entry = _describe(n, "direct")
        if entry is not None:
            dev.append(entry)
    for n in transitive:
        entry = _describe(n, "transitive")
        if entry is not None:
            dev.append(entry)
    return {
        "sbom_version": "1.0",
        "project": "ao-runtime-operator",
        "internal_slug": "ao-operator",
        "language": "python",
        "runtime_dependencies": [],
        "runtime_dependencies_note": (
            "Default production code in scripts/ is stdlib-only. "
            "Optional production features use lazy dependencies listed separately."
        ),
        "optional_production_dependencies": OPTIONAL_PRODUCTION_DEPENDENCIES,
        "dev_dependencies": dev,
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "generator": "importlib.metadata (stdlib)",
    }


def main() -> int:
    json.dump(build_sbom(), sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
