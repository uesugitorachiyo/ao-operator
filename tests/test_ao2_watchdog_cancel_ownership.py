from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ao2_watchdog_cancel_ownership.py"

WATCHDOG_SCHEMA = "ao-operator/hermes-ao2-watchdog/v1"
TRANSITION_SCHEMA = "ao2.ao-operator-compat-workbench-queue-transition.v1"
ATTESTATION_SCHEMA = "ao-operator/ao2-watchdog-no-active-ao2-runs-attestation/v1"
OUTPUT_SCHEMA = "ao-operator/ao2-watchdog-cancel-ownership/v1"


def watchdog_fixture(
    *,
    action: str = "started_hermes_oneshot",
    terminated_pid: int | None = None,
    extra: dict | None = None,
) -> dict:
    payload = {
        "schema": WATCHDOG_SCHEMA,
        "action": action,
        "active_pid": 999,
        "lock_age_seconds": 120.0,
    }
    if terminated_pid is not None:
        payload["terminated_pid"] = terminated_pid
    if extra:
        payload.update(extra)
    return payload


def transition_fixture(
    *,
    terminated_pid: int | None = None,
    status: str = "cancelled",
    run_id: str = "factory-compat-20260524-watchdog-recovery",
) -> dict:
    entry = {
        "schema_version": "ao2.ao-operator-compat-workbench-queue-entry.v1",
        "run_id": run_id,
        "status": status,
        "attempts": 1,
        "transition_history": [
            {"at": "2026-05-24T05:00:00Z", "from": "running", "status": status},
        ],
    }
    if terminated_pid is not None:
        entry["terminated_pid"] = terminated_pid
        entry["transition_history"][0]["terminated_pid"] = terminated_pid
    return {
        "schema_version": TRANSITION_SCHEMA,
        "factory_v3_role": "parity_oracle_only",
        "ao2_decision_owner": "ao2-workbench-queue",
        "run_id": run_id,
        "entry": entry,
    }


def attestation_fixture(*, no_active: bool = True) -> dict:
    return {
        "schema": ATTESTATION_SCHEMA,
        "factory_v3_role": "parity_oracle_only",
        "no_active_ao2_runs": no_active,
        "attested_at": "2026-05-24T05:01:00Z",
        "attested_by": "parity-oracle",
    }


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _run(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *[str(a) for a in args]],
        capture_output=True,
        text=True,
        check=False,
    )


def test_no_termination_accepts_without_transitions(tmp_path: Path) -> None:
    status_path = _write_json(tmp_path / "watchdog.json", watchdog_fixture())
    out_path = tmp_path / "out.json"
    result = _run("--watchdog-status", status_path, "--write-json", out_path)
    assert result.returncode == 0, result.stderr
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["schema"] == OUTPUT_SCHEMA
    assert payload["status"] == "accepted"
    assert payload["decision"] == "accept_ao2_owns_watchdog_cancel"
    assert payload["watchdog_terminated_a_process"] is False
    assert payload["terminated_pids"] == []
    assert payload["blockers"] == []


def test_termination_with_matching_transition_accepts(tmp_path: Path) -> None:
    status_path = _write_json(
        tmp_path / "watchdog.json",
        watchdog_fixture(
            action="recovered_overdue_hermes_oneshot", terminated_pid=4242
        ),
    )
    transition_path = _write_json(
        tmp_path / "transition.json", transition_fixture(terminated_pid=4242)
    )
    out_path = tmp_path / "out.json"
    md_path = tmp_path / "out.md"
    result = _run(
        "--watchdog-status",
        status_path,
        "--transition",
        transition_path,
        "--write-json",
        out_path,
        "--write-md",
        md_path,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["status"] == "accepted"
    assert payload["transition_count"] == 1
    assert payload["pid_coverage"][0]["covered"] is True
    assert payload["pid_coverage"][0]["covered_by_transition_indexes"] == [0]
    rendered_md = md_path.read_text(encoding="utf-8")
    assert "accept_ao2_owns_watchdog_cancel" in rendered_md
    assert "4242" in rendered_md


def test_termination_without_evidence_blocks(tmp_path: Path) -> None:
    status_path = _write_json(
        tmp_path / "watchdog.json",
        watchdog_fixture(
            action="recovered_overdue_hermes_oneshot", terminated_pid=4242
        ),
    )
    out_path = tmp_path / "out.json"
    result = _run("--watchdog-status", status_path, "--write-json", out_path)
    assert result.returncode == 1, result.stderr
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert payload["decision"] == "reject_factory_v3_retained_cancel_authority"
    assert payload["blockers"]
    assert "no AO2 cancel transitions" in payload["blockers"][0]


def test_termination_with_uncovered_pid_blocks(tmp_path: Path) -> None:
    status_path = _write_json(
        tmp_path / "watchdog.json",
        watchdog_fixture(
            action="recovered_overdue_hermes_oneshot", terminated_pid=4242
        ),
    )
    transition_path = _write_json(
        tmp_path / "transition.json", transition_fixture(terminated_pid=9999)
    )
    out_path = tmp_path / "out.json"
    result = _run(
        "--watchdog-status",
        status_path,
        "--transition",
        transition_path,
        "--write-json",
        out_path,
    )
    assert result.returncode == 1, result.stderr
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert any("missing AO2 cancel transition coverage" in b for b in payload["blockers"])
    assert payload["pid_coverage"][0]["covered"] is False


def test_attestation_authorises_termination_with_no_in_flight_run(tmp_path: Path) -> None:
    status_path = _write_json(
        tmp_path / "watchdog.json",
        watchdog_fixture(
            action="recovered_overdue_hermes_oneshot", terminated_pid=4242
        ),
    )
    attestation_path = _write_json(tmp_path / "attest.json", attestation_fixture())
    out_path = tmp_path / "out.json"
    result = _run(
        "--watchdog-status",
        status_path,
        "--no-active-ao2-runs-attestation",
        attestation_path,
        "--write-json",
        out_path,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["status"] == "accepted"
    assert payload["no_active_ao2_runs_attestation_provided"] is True


def test_local_cancel_decision_refuses(tmp_path: Path) -> None:
    status_path = _write_json(tmp_path / "watchdog.json", watchdog_fixture())
    local_path = _write_json(tmp_path / "local.json", {"decision": "cancel"})
    result = _run(
        "--watchdog-status",
        status_path,
        "--local-cancel-decision",
        local_path,
    )
    assert result.returncode == 2
    assert "cancel ownership cannot be local" in result.stderr


def test_invalid_watchdog_schema_refuses(tmp_path: Path) -> None:
    status_path = _write_json(tmp_path / "watchdog.json", {"schema": "other"})
    result = _run("--watchdog-status", status_path)
    assert result.returncode == 2
    assert "watchdog status schema must be" in result.stderr


@pytest.mark.parametrize(
    "mutation,fragment",
    [
        ({"schema_version": "other"}, "transition schema must be"),
        ({"factory_v3_role": "executor"}, "factory_v3_role must be"),
        ({"ao2_decision_owner": "other"}, "ao2_decision_owner must be"),
    ],
)
def test_invalid_transition_refuses(
    tmp_path: Path, mutation: dict, fragment: str
) -> None:
    status_path = _write_json(
        tmp_path / "watchdog.json",
        watchdog_fixture(
            action="recovered_overdue_hermes_oneshot", terminated_pid=42
        ),
    )
    transition = transition_fixture(terminated_pid=42)
    transition.update(mutation)
    transition_path = _write_json(tmp_path / "transition.json", transition)
    result = _run(
        "--watchdog-status",
        status_path,
        "--transition",
        transition_path,
    )
    assert result.returncode == 2
    assert fragment in result.stderr


def test_invalid_transition_status_refuses(tmp_path: Path) -> None:
    status_path = _write_json(
        tmp_path / "watchdog.json",
        watchdog_fixture(
            action="recovered_overdue_hermes_oneshot", terminated_pid=42
        ),
    )
    transition = transition_fixture(terminated_pid=42, status="completed")
    transition_path = _write_json(tmp_path / "transition.json", transition)
    result = _run(
        "--watchdog-status",
        status_path,
        "--transition",
        transition_path,
    )
    assert result.returncode == 2
    assert "transition must record status 'cancelled'" in result.stderr


def test_invalid_attestation_refuses(tmp_path: Path) -> None:
    status_path = _write_json(
        tmp_path / "watchdog.json",
        watchdog_fixture(
            action="recovered_overdue_hermes_oneshot", terminated_pid=42
        ),
    )
    bad = attestation_fixture(no_active=False)
    attestation_path = _write_json(tmp_path / "attest.json", bad)
    result = _run(
        "--watchdog-status",
        status_path,
        "--no-active-ao2-runs-attestation",
        attestation_path,
    )
    assert result.returncode == 2
    assert "no_active_ao2_runs must be true" in result.stderr


def test_invalid_attestation_factory_role_refuses(tmp_path: Path) -> None:
    status_path = _write_json(
        tmp_path / "watchdog.json",
        watchdog_fixture(
            action="recovered_overdue_hermes_oneshot", terminated_pid=42
        ),
    )
    bad = attestation_fixture()
    bad["factory_v3_role"] = "executor"
    attestation_path = _write_json(tmp_path / "attest.json", bad)
    result = _run(
        "--watchdog-status",
        status_path,
        "--no-active-ao2-runs-attestation",
        attestation_path,
    )
    assert result.returncode == 2
    assert "factory_v3_role must be" in result.stderr


def test_multiple_pids_partial_coverage_blocks(tmp_path: Path) -> None:
    status_path = _write_json(
        tmp_path / "watchdog.json",
        watchdog_fixture(
            action="recovered_overdue_hermes_oneshot",
            terminated_pid=42,
            extra={"terminated_pids": [42, 99]},
        ),
    )
    transition_path = _write_json(
        tmp_path / "transition.json", transition_fixture(terminated_pid=42)
    )
    out_path = tmp_path / "out.json"
    result = _run(
        "--watchdog-status",
        status_path,
        "--transition",
        transition_path,
        "--write-json",
        out_path,
    )
    assert result.returncode == 1, result.stderr
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    uncovered = [c for c in payload["pid_coverage"] if not c["covered"]]
    assert len(uncovered) == 1
    assert uncovered[0]["terminated_pid"] == 99


def test_missing_input_file_errors(tmp_path: Path) -> None:
    result = _run("--watchdog-status", tmp_path / "missing.json")
    assert result.returncode != 0
    assert "missing input" in result.stderr
