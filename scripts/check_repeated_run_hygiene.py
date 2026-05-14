#!/usr/bin/env python3
"""Check same-slug repeated-run hygiene without running providers."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import check_live_acceptance
import route_live_postrun


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLUG = "remote-transfer-v2-stress-live"
DEFAULT_OUTPUT = "run-artifacts/remote-transfer-v2-stress-live/dispatch/repeated-run-hygiene.json"


def write_accepted_live(root: Path, slug: str = DEFAULT_SLUG) -> None:
    eval_path = root / "docs" / "evaluations" / f"{slug}-evaluation.md"
    status_dir = root / "run-artifacts" / slug
    eval_path.parent.mkdir(parents=True, exist_ok=True)
    status_dir.mkdir(parents=True, exist_ok=True)
    eval_path.write_text(
        "\n".join(
            [
                "Verdict: ACCEPTED",
                "AO Run: r-accepted-live",
                "",
                "Blockers:",
                "",
                "- none",
            ]
        ),
        encoding="utf-8",
    )
    (status_dir / f"{slug}-status.md").write_text(
        "\n".join(
            [
                f"# {slug} Status",
                "",
                "Mode: run",
                "AO Run: r-accepted-live",
                "",
                "## Gate",
                "",
                "- Blocked: false",
            ]
        ),
        encoding="utf-8",
    )
    (status_dir / f"{slug}-ao-events.md").write_text("AO command exit=0\nAO completed=true\n", encoding="utf-8")


def redact_tmp_root(value: Any, root: Path) -> Any:
    if isinstance(value, str):
        return value.replace(str(root), "<scenario-root>")
    if isinstance(value, list):
        return [redact_tmp_root(item, root) for item in value]
    if isinstance(value, dict):
        return {key: redact_tmp_root(item, root) for key, item in value.items()}
    return value


def scenario_result(
    scenario_id: str,
    passed: bool,
    detail: str,
    payload: dict[str, Any] | None = None,
    *,
    root: Path,
) -> dict[str, Any]:
    return {
        "id": scenario_id,
        "verdict": "PASS" if passed else "FAIL",
        "detail": detail,
        "payload": redact_tmp_root(payload or {}, root),
    }


def same_slug_dry_run_after_live(root: Path) -> dict[str, Any]:
    slug = DEFAULT_SLUG
    write_accepted_live(root, slug)
    status = root / "run-artifacts" / slug / f"{slug}-status.md"
    status.write_text("Mode: dry-run\nAO Run: none\n- Blocked: false\n", encoding="utf-8")

    acceptance = check_live_acceptance.check_slug(slug, root=root)
    statuses = {check["id"]: check["status"] for check in acceptance["checks"]}
    passed = acceptance["verdict"] == "FAIL" and statuses.get("mode.run") == "FAIL"
    return scenario_result(
        "same-slug-dry-run-after-live",
        passed,
        "dry-run status must not inherit accepted live evidence",
        acceptance,
        root=root,
    )


def live_after_failed_live(root: Path) -> dict[str, Any]:
    slug = DEFAULT_SLUG
    write_accepted_live(root, slug)
    events = root / "run-artifacts" / slug / f"{slug}-ao-events.md"
    events.write_text(
        "\n".join(
            [
                "AO command exit=1",
                "AO completed=false",
                '{"kind":"task.failed","payload":{"normalized_reason":"provider-rate-limit"}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    acceptance = check_live_acceptance.check_slug(slug, root=root)
    statuses = {check["id"]: check["status"] for check in acceptance["checks"]}
    passed = (
        acceptance["verdict"] == "FAIL"
        and statuses.get("ao_command_exit.zero") == "FAIL"
        and statuses.get("ao_completed.true") == "FAIL"
    )
    return scenario_result(
        "live-after-failed-live",
        passed,
        "failed same-slug events must block stale accepted evaluation/status",
        acceptance,
        root=root,
    )


def reroute_after_accepted_live(root: Path) -> dict[str, Any]:
    slug = DEFAULT_SLUG
    write_accepted_live(root, slug)
    classification = root / "classification.json"
    classification.write_text(
        json.dumps(
            {
                "schema": "ao-operator/live-outcome-classification/v1",
                "classification": "PENDING_LIVE_RUN",
                "diagnostics_required": False,
            }
        ),
        encoding="utf-8",
    )
    plan = root / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "schema": "ao-operator/live-failure-diagnostics-plan/v1",
                "slug": slug,
                "classification": "PENDING_LIVE_RUN",
                "diagnostics_required": False,
                "copy_allowed": False,
                "raw_snapshot_commit_allowed": False,
                "live_providers_run": False,
            }
        ),
        encoding="utf-8",
    )

    route = route_live_postrun.route(root=root, slug=slug, classification_path=classification, plan_path=plan)
    passed = route["verdict"] == "FAIL" and any(
        "non-accepted classification conflicts with live acceptance PASS" in error for error in route["errors"]
    )
    return scenario_result(
        "reroute-after-accepted-live",
        passed,
        "postrun routing must reject pending reroute when accepted live evidence is present",
        route,
        root=root,
    )


def check(*, root: Path = ROOT) -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    for scenario in (same_slug_dry_run_after_live, live_after_failed_live, reroute_after_accepted_live):
        with tempfile.TemporaryDirectory(prefix=f"ao-operator-{scenario.__name__}-") as tmp:
            scenarios.append(scenario(Path(tmp)))
    return {
        "schema": "ao-operator/repeated-run-hygiene/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": "PASS" if all(item["verdict"] == "PASS" for item in scenarios) else "FAIL",
        "repo": "${FACTORY_V3_ROOT}",
        "scenarios": scenarios,
        "dispatch_authorized": False,
        "live_providers_run": False,
        "next_actions": [
            "Keep reruns isolated by classification and route evidence.",
            "Do not commit same-slug dry-run or failed-live artifacts as accepted live evidence.",
        ],
    }


def resolve_output(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def write_output(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check repeated-run hygiene guards")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-output", nargs="?", const=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = check(root=args.root)
    if args.write_output is not None:
        output = resolve_output(args.root, args.write_output)
        write_output(output, payload)
        payload["output"] = relpath(args.root, output)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"verdict={payload['verdict']}")
        for scenario in payload["scenarios"]:
            print(f"{scenario['verdict']} {scenario['id']}: {scenario['detail']}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
