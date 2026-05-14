#!/usr/bin/env python3
"""Provider-free public-launch smoke for AO Operator.

The smoke copies the repository to a temporary clean workspace, runs the
copy-pasteable first-run and SDD-ingestion demos there, and writes a compact
report back to the source checkout. It intentionally does not dispatch live
providers or require Codex/Claude auth.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ao-operator/public-launch-smoke/v1"
FORBIDDEN_PROVIDER_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")
REPORT_DIR = ROOT / "run-artifacts" / "public-launch-smoke"


DEMOS = [
    {
        "id": "first-run-agent-team",
        "brief": "examples/agent-team-demo/task-brief.md",
        "profile": "bug-fix",
        "slug": "public-launch-first-run",
    },
    {
        "id": "ingest-financial-citation-audit-sdd",
        "brief": "examples/ingestible-specs/financial-citation-audit-sdd.md",
        "profile": "smoke-test",
        "slug": "public-launch-financial-citation-audit",
    },
    {
        "id": "ingest-service-booking-sdd",
        "brief": "examples/ingestible-specs/service-booking-recovery-sdd.md",
        "profile": "greenfield",
        "slug": "public-launch-service-booking",
    },
    {
        "id": "ingest-bug-fix-sdd",
        "brief": "examples/ingestible-specs/bug-fix-sdd.md",
        "profile": "bug-fix",
        "slug": "public-launch-bug-fix",
    },
    {
        "id": "ingest-three-os-setup-sdd",
        "brief": "examples/ingestible-specs/three-os-setup-sdd.md",
        "profile": "smoke-test",
        "slug": "public-launch-three-os-setup",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run(command: list[str], *, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def ignore_names(_: str, names: list[str]) -> set[str]:
    ignored = {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        "dist",
        "build",
    }
    return {name for name in names if name in ignored}


def copy_to_clean_workspace(source: Path, target: Path) -> None:
    shutil.copytree(source, target, ignore=ignore_names)
    status_readme = target / "run-artifacts" / "README.md"
    status_readme_body = status_readme.read_text(encoding="utf-8") if status_readme.is_file() else "# Status\n"
    shutil.rmtree(target / "run-artifacts", ignore_errors=True)
    (target / "run-artifacts").mkdir(parents=True, exist_ok=True)
    status_readme.write_text(status_readme_body, encoding="utf-8")
    run(["git", "init", "-q"], cwd=target)
    run(["git", "add", "-A"], cwd=target)
    run(
        [
            "git",
            "-c",
            "user.name=AO Runtime",
            "-c",
            "user.email=270548076+uesugitorachiyo@users.noreply.github.com",
            "commit",
            "-qm",
            "public launch smoke baseline",
        ],
        cwd=target,
    )


def remove_transient_git_dir(workspace: Path) -> None:
    """Remove the temporary Git repo before TemporaryDirectory cleanup.

    The smoke needs a clean Git repo while materializing demo artifacts, but the
    resulting `.git` directory is not part of the report. Removing it explicitly
    avoids macOS/Python temp cleanup races where `.git/info/refs` or
    `.git/objects/info/packs` can be left behind long enough for rmtree to fail.
    """

    git_dir = workspace / ".git"
    if not git_dir.exists():
        return

    def on_rm_error(function: Any, path: str, _: Any) -> None:
        target = Path(path)
        try:
            target.chmod(stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass
        function(path)

    for attempt in range(5):
        try:
            shutil.rmtree(git_dir, onerror=on_rm_error)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt == 4:
                raise
            time.sleep(0.2)


def expected_artifacts(slug: str) -> list[str]:
    return [
        f"run-artifacts/{slug}",
        f"run-artifacts/{slug}/{slug}-status.md",
        f"run-artifacts/{slug}/{slug}.runspec.yaml",
        f"docs/specs/{slug}-spec.md",
        f"docs/plans/{slug}-plan.md",
    ]


def run_demo(workspace: Path, demo: dict[str, str]) -> dict[str, Any]:
    slug = demo["slug"]
    specify = run(
        [
            sys.executable,
            "scripts/factory_run.py",
            "specify",
            demo["brief"],
            "--slug",
            slug,
            "--profile",
            demo["profile"],
            "--overwrite-artifacts",
        ],
        cwd=workspace,
    )
    tasks = run(
        [
            sys.executable,
            "scripts/factory_run.py",
            "tasks",
            slug,
            "--profile",
            demo["profile"],
            "--json",
        ],
        cwd=workspace,
    )
    artifacts = [
        {"path": rel, "present": (workspace / rel).exists()}
        for rel in expected_artifacts(slug)
    ]
    ok = specify["returncode"] == 0 and tasks["returncode"] == 0 and all(
        item["present"] for item in artifacts
    )
    return {
        "id": demo["id"],
        "brief": demo["brief"],
        "profile": demo["profile"],
        "slug": slug,
        "status": "PASS" if ok else "FAIL",
        "specify": specify,
        "tasks": tasks,
        "artifacts": artifacts,
    }


def build_report(*, keep_workspace: bool = False) -> dict[str, Any]:
    present_keys = [key for key in FORBIDDEN_PROVIDER_KEYS if os.environ.get(key)]
    if present_keys:
        return {
            "schema": SCHEMA,
            "generated_at": utc_now(),
            "status": "FAIL",
            "provider_dispatch": False,
            "forbidden_provider_api_keys_present": present_keys,
            "demos": [],
        }

    with tempfile.TemporaryDirectory(prefix="ao-operator-public-launch-smoke.") as tmp:
        workspace = Path(tmp) / "ao-operator"
        try:
            copy_to_clean_workspace(ROOT, workspace)
            scaffold = run([sys.executable, "scripts/validate_scaffold.py", "--json"], cwd=workspace)
            demos = [run_demo(workspace, demo) for demo in DEMOS]
            if keep_workspace:
                preserved = Path(tempfile.mkdtemp(prefix="ao-operator-public-launch-smoke-kept."))
                shutil.copytree(workspace, preserved / "ao-operator")
                workspace_hint: str | None = str(preserved / "ao-operator")
            else:
                workspace_hint = None
        finally:
            remove_transient_git_dir(workspace)

    status = "PASS" if scaffold["returncode"] == 0 and all(d["status"] == "PASS" for d in demos) else "FAIL"
    return {
        "schema": SCHEMA,
        "generated_at": utc_now(),
        "status": status,
        "provider_dispatch": False,
        "forbidden_provider_api_keys_present": [],
        "clean_workspace": "temporary copy; source checkout not mutated by demo commands",
        "kept_workspace": workspace_hint,
        "scaffold": scaffold,
        "demos": demos,
    }


def write_report(report: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "latest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = [
        "# AO Operator Public Launch Smoke",
        "",
        f"Status: {report['status']}",
        f"Generated: {report['generated_at']}",
        f"Schema: `{SCHEMA}`",
        "",
        "Provider dispatch: false",
        "Workspace: temporary clean copy; source checkout is not used for generated demo artifacts.",
        "",
        "| Demo | Profile | Slug | Status |",
        "|---|---|---|---|",
    ]
    for demo in report["demos"]:
        rows.append(f"| `{demo['id']}` | `{demo['profile']}` | `{demo['slug']}` | {demo['status']} |")
    rows.extend(
        [
            "",
            "The smoke proves the first public path can materialize role graphs, specs,",
            "plans, status files, and RunSpecs without provider credentials. Live Codex",
            "or Claude execution remains a separate authenticated step.",
            "",
        ]
    )
    (REPORT_DIR / "latest.md").write_text("\n".join(rows), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AO Operator public-launch smoke")
    parser.add_argument("--json", action="store_true", help="print machine-readable report")
    parser.add_argument("--no-write-report", action="store_true", help="do not write run-artifacts report")
    parser.add_argument("--keep-workspace", action="store_true", help="preserve temporary smoke workspace")
    args = parser.parse_args()

    report = build_report(keep_workspace=args.keep_workspace)
    if not args.no_write_report:
        write_report(report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"status={report['status']}")
        print(f"report={REPORT_DIR / 'latest.md'}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
