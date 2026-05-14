from __future__ import annotations

import json
from pathlib import Path

import check_live_acceptance


def write_live_artifacts(root: Path, *, accepted: bool = True, run_id: str = "r-live-123") -> None:
    slug = "remote-transfer-v2-stress-live"
    eval_path = root / "docs" / "evaluations" / f"{slug}-evaluation.md"
    status_dir = root / "run-artifacts" / slug
    eval_path.parent.mkdir(parents=True)
    status_dir.mkdir(parents=True)
    eval_path.write_text(
        "\n".join(
            [
                f"Verdict: {'ACCEPTED' if accepted else 'REJECTED'}",
                f"AO Run: {run_id}",
                "",
                "## Blockers",
                "",
                "Blockers: none" if accepted else "Blockers: provider-limit",
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
                f"AO Run: {run_id}",
                "",
                "## Gate",
                "",
                "- Blocked: false",
            ]
        ),
        encoding="utf-8",
    )
    (status_dir / f"{slug}-ao-events.md").write_text(
        "\n".join(["AO command exit=0", "AO completed=true"]),
        encoding="utf-8",
    )


def test_check_slug_accepts_complete_live_artifacts(tmp_path):
    write_live_artifacts(tmp_path)

    payload = check_live_acceptance.check_slug("remote-transfer-v2-stress-live", root=tmp_path)

    assert payload["verdict"] == "PASS"
    assert {check["id"]: check["status"] for check in payload["checks"]}["ao_run.real"] == "PASS"


def test_check_slug_accepts_accepted_eval_with_rejected_concern_and_raw_event(tmp_path):
    write_live_artifacts(tmp_path)
    slug = "remote-transfer-v2-stress-live"
    eval_path = tmp_path / "docs" / "evaluations" / f"{slug}-evaluation.md"
    eval_path.write_text(
        "\n".join(
            [
                "Verdict: ACCEPTED",
                "AO Run: r-live-123",
                "",
                "Concerns:",
                "",
                "- At least one role returned BLOCKED or REJECTED.",
                "",
                "Blockers:",
                "",
                "- none",
            ]
        ),
        encoding="utf-8",
    )
    event_path = tmp_path / "run-artifacts" / slug / f"{slug}-ao-events.md"
    event_path.write_text(
        "\n".join(["AO command exit=0", "AO completed=true", "raw stdout Result: REJECTED"]),
        encoding="utf-8",
    )

    payload = check_live_acceptance.check_slug(slug, root=tmp_path)

    statuses = {check["id"]: check["status"] for check in payload["checks"]}
    assert payload["verdict"] == "PASS"
    assert statuses["blockers.none"] == "PASS"


def test_check_slug_rejects_dry_run_status(tmp_path):
    write_live_artifacts(tmp_path, run_id="none")

    payload = check_live_acceptance.check_slug("remote-transfer-v2-stress-live", root=tmp_path)

    assert payload["verdict"] == "FAIL"
    statuses = {check["id"]: check["status"] for check in payload["checks"]}
    assert statuses["ao_run.real"] == "FAIL"


def test_check_slug_rejects_missing_events(tmp_path):
    write_live_artifacts(tmp_path)
    slug_dir = tmp_path / "run-artifacts" / "remote-transfer-v2-stress-live"
    (slug_dir / "remote-transfer-v2-stress-live-ao-events.md").unlink()

    payload = check_live_acceptance.check_slug("remote-transfer-v2-stress-live", root=tmp_path)

    assert payload["verdict"] == "FAIL"
    statuses = {check["id"]: check["status"] for check in payload["checks"]}
    assert statuses["events.exists"] == "FAIL"


def test_main_emits_json_and_nonzero_on_failure(tmp_path, capsys):
    result = check_live_acceptance.main(
        ["--slug", "remote-transfer-v2-stress-live", "--root", str(tmp_path), "--json"]
    )

    assert result == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "FAIL"
