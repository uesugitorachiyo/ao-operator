#!/usr/bin/env python3
"""Run the deterministic financial-services SEC EDGAR demo wiring."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import sec_edgar_public_source_pack

SCHEMA = "ao-operator/financial-services-sec-edgar-demo/v1"
PROFILE = "financial-services:earnings-note"
DEFAULT_SLUG = "financial-services-mvp-demo"


def _rel(root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(root.resolve()))
    except ValueError:
        return str(resolved)


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Financial-Services SEC EDGAR Demo Wiring",
        "",
        f"Schema: `{report['schema']}`",
        f"Status: `{report['status']}`",
        f"Profile: `{report['profile']}`",
        f"Ticker / quarter: `{report['ticker']} / {report['quarter']}`",
        "",
        "## Artifacts",
        "",
    ]
    for key, value in report["artifacts"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(
        [
            "",
            "## Factory Dry Run",
            "",
            "```sh",
            " ".join(report["factory_command"]),
            "```",
            "",
            f"Exit code: `{report['factory_exit_code']}`",
            "",
            "## Boundaries",
            "",
            "- Public SEC EDGAR fixture only; no paid connectors.",
            "- No live network fetch in this deterministic demo shim.",
            "- No investment recommendation, compliance certification, or financial accuracy claim.",
            "- Dry run renders AO Operator artifacts; live provider dispatch remains a separate human-approved lane.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def run_demo(
    *,
    root: Path,
    ticker: str,
    quarter: str,
    slug: str,
    status_dir: Path,
    run_factory: bool,
) -> dict[str, Any]:
    demo_dir = status_dir / slug
    source_pack_dir = demo_dir / "source-pack" / "sec-edgar"
    source_manifest = sec_edgar_public_source_pack.write_source_pack(
        ticker, quarter, source_pack_dir
    )

    brief = root / "run-artifacts/financial-services-mvp/sec-edgar-demo-fixture.md"
    factory_command = [
        sys.executable,
        "scripts/factory_run.py",
        "--brief",
        _rel(root, brief),
        "--slug",
        slug,
        "--profile",
        PROFILE,
        "--dry-run",
        "--overwrite-artifacts",
    ]
    factory_exit_code = 0
    if run_factory:
        completed = subprocess.run(factory_command, cwd=root, check=False)
        factory_exit_code = completed.returncode

    runspec = demo_dir / f"{slug}.runspec.yaml"
    if runspec.exists():
        runspec.write_text(
            runspec.read_text(encoding="utf-8").replace(str(root), "${FACTORY_V3_ROOT}"),
            encoding="utf-8",
        )
    report = {
        "schema": SCHEMA,
        "status": "PASS" if factory_exit_code == 0 else "FAIL",
        "ticker": ticker.strip().upper(),
        "quarter": quarter.strip().upper(),
        "profile": PROFILE,
        "slug": slug,
        "source_manifest_schema": source_manifest["schema"],
        "factory_exit_code": factory_exit_code,
        "factory_command": factory_command,
        "artifacts": {
            "source_manifest": _rel(root, source_pack_dir / "manifest.json"),
            "source_filing_summary": _rel(root, source_pack_dir / "filing-summary.md"),
            "source_metric_spans": _rel(root, source_pack_dir / "metric-spans.json"),
            "runspec": _rel(root, runspec),
            "prompts_dir": _rel(root, demo_dir / "prompts"),
            "status_markdown": _rel(root, demo_dir / "sec-edgar-demo.md"),
            "status_json": _rel(root, demo_dir / "sec-edgar-demo.json"),
        },
    }
    demo_dir.mkdir(parents=True, exist_ok=True)
    (demo_dir / "sec-edgar-demo.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_markdown(report, demo_dir / "sec-edgar-demo.md")
    if factory_exit_code != 0:
        raise SystemExit(factory_exit_code)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="NVDA")
    parser.add_argument("--quarter", default="2026Q1")
    parser.add_argument("--slug", default=DEFAULT_SLUG)
    parser.add_argument("--status-dir", type=Path, default=Path("run-artifacts"))
    parser.add_argument("--no-factory-dry-run", action="store_true")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    report = run_demo(
        root=root,
        ticker=args.ticker,
        quarter=args.quarter,
        slug=args.slug,
        status_dir=(root / args.status_dir).resolve()
        if not args.status_dir.is_absolute()
        else args.status_dir,
        run_factory=not args.no_factory_dry_run,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
