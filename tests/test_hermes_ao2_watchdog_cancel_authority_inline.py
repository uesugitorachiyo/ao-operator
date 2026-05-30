"""Tests for the live AO2 cancel-authority consultation in hermes_ao2_watchdog.

Phase 2 exit-gate item #5 follow-up slice: the previous commit (434e42a9)
added an after-the-fact ownership-claim emitter
(``scripts/ao2_watchdog_cancel_ownership.py``). This slice wires the live
watchdog source itself so the ``recover_overdue`` branch consults AO2
cancel authority before terminating a Hermes one-shot, and records the
inline authority claim in the watchdog status payload.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hermes_ao2_watchdog.py"

TRANSITION_SCHEMA = "ao2.ao-operator-compat-workbench-queue-transition.v1"
ATTESTATION_SCHEMA = "ao-operator/ao2-watchdog-no-active-ao2-runs-attestation/v1"
EXPECTED_FACTORY_V3_ROLE = "parity_oracle_only"
EXPECTED_AO2_DECISION_OWNER = "ao2-workbench-queue"


def _make_fake_hermes(tmp_path: Path) -> Path:
    fake_hermes = tmp_path / "hermes"
    fake_hermes.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "import time",
                "time.sleep(2)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fake_hermes.chmod(0o755)
    return fake_hermes


def _seed_overdue_lock(
    tmp_path: Path, status_dir: Path
) -> tuple[subprocess.Popen[bytes], Path]:
    lock_dir = status_dir / "ao2-watchdog.lock"
    lock_dir.mkdir(parents=True)
    old_child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    (lock_dir / "pid").write_text(str(old_child.pid) + "\n", encoding="utf-8")
    old = time.time() - 120
    os.utime(lock_dir, (old, old))
    return old_child, lock_dir


def _run_watchdog(
    status_dir: Path, fake_hermes: Path, *extra: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--factory-root",
            str(ROOT),
            "--status-dir",
            str(status_dir),
            "--hermes-bin",
            str(fake_hermes),
            "--max-lock-age-minutes",
            "1",
            "--recover-overdue",
            "--json",
            *extra,
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _write_transition(path: Path, *, terminated_pid: int) -> None:
    payload = {
        "schema_version": TRANSITION_SCHEMA,
        "factory_v3_role": EXPECTED_FACTORY_V3_ROLE,
        "ao2_decision_owner": EXPECTED_AO2_DECISION_OWNER,
        "entry": {
            "status": "cancelled",
            "terminated_pid": terminated_pid,
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_attestation(path: Path) -> None:
    payload = {
        "schema": ATTESTATION_SCHEMA,
        "factory_v3_role": EXPECTED_FACTORY_V3_ROLE,
        "no_active_ao2_runs": True,
        "reason": "Hermes one-shot stuck without an in-flight AO2 run to cancel",
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_recover_overdue_legacy_mode_records_pending_source_wiring_claim(
    tmp_path: Path,
) -> None:
    status_dir = tmp_path / "watchdog"
    old_child, _ = _seed_overdue_lock(tmp_path, status_dir)
    fake_hermes = _make_fake_hermes(tmp_path)
    try:
        result = _run_watchdog(status_dir, fake_hermes)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["action"] == "recovered_overdue_hermes_oneshot"
        authority = payload.get("ao2_cancel_authority") or {}
        assert authority.get("mode") == "factory_v3_unilateral_legacy_pending_source_wiring"
        assert authority.get("decision") == "allow_unilateral_legacy"
        assert (
            authority.get("warning")
            == "ao-operator retained cancel authority; supply --ao2-cancel-transition "
            "or --no-active-ao2-runs-attestation to record AO2-owned authority inline"
        )
        assert authority.get("ao2_ownership") == {
            "cancel_owner": EXPECTED_AO2_DECISION_OWNER,
            "retry_owner": EXPECTED_AO2_DECISION_OWNER,
            "factory_v3_role": EXPECTED_FACTORY_V3_ROLE,
        }
        # legacy mode still terminates the old process
        for _ in range(40):
            if old_child.poll() is not None:
                break
            time.sleep(0.05)
        assert old_child.poll() is not None
    finally:
        if old_child.poll() is None:
            old_child.terminate()
            old_child.wait(timeout=5)


def test_recover_overdue_with_valid_cancel_transition_records_accepted_inline_claim(
    tmp_path: Path,
) -> None:
    status_dir = tmp_path / "watchdog"
    old_child, _ = _seed_overdue_lock(tmp_path, status_dir)
    fake_hermes = _make_fake_hermes(tmp_path)
    transition_path = tmp_path / "cancel-transition.json"
    _write_transition(transition_path, terminated_pid=old_child.pid)
    try:
        result = _run_watchdog(
            status_dir,
            fake_hermes,
            "--ao2-cancel-transition",
            str(transition_path),
            "--require-ao2-cancel-authority",
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["action"] == "recovered_overdue_hermes_oneshot"
        authority = payload.get("ao2_cancel_authority") or {}
        assert authority.get("mode") == "ao2_owned"
        assert authority.get("decision") == "accept_ao2_owns_watchdog_cancel"
        claim = authority.get("claim") or {}
        assert claim.get("status") == "accepted"
        assert claim.get("terminated_pids") == [old_child.pid]
        pid_coverage = claim.get("pid_coverage") or []
        assert pid_coverage and pid_coverage[0]["covered"] is True
        sources = authority.get("sources") or {}
        assert sources.get("transitions") == [str(transition_path)]
        assert sources.get("no_active_ao2_runs_attestation") is None
        # process should still be terminated under valid AO2 authority
        for _ in range(40):
            if old_child.poll() is not None:
                break
            time.sleep(0.05)
        assert old_child.poll() is not None
    finally:
        if old_child.poll() is None:
            old_child.terminate()
            old_child.wait(timeout=5)


def test_recover_overdue_with_no_active_attestation_records_accepted_inline_claim(
    tmp_path: Path,
) -> None:
    status_dir = tmp_path / "watchdog"
    old_child, _ = _seed_overdue_lock(tmp_path, status_dir)
    fake_hermes = _make_fake_hermes(tmp_path)
    attestation_path = tmp_path / "no-active-attestation.json"
    _write_attestation(attestation_path)
    try:
        result = _run_watchdog(
            status_dir,
            fake_hermes,
            "--no-active-ao2-runs-attestation",
            str(attestation_path),
            "--require-ao2-cancel-authority",
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["action"] == "recovered_overdue_hermes_oneshot"
        authority = payload.get("ao2_cancel_authority") or {}
        assert authority.get("mode") == "ao2_owned"
        claim = authority.get("claim") or {}
        assert claim.get("status") == "accepted"
        assert claim.get("no_active_ao2_runs_attestation_provided") is True
        sources = authority.get("sources") or {}
        assert sources.get("no_active_ao2_runs_attestation") == str(attestation_path)
    finally:
        if old_child.poll() is None:
            old_child.terminate()
            old_child.wait(timeout=5)


def test_recover_overdue_with_require_flag_no_source_refuses_termination(
    tmp_path: Path,
) -> None:
    status_dir = tmp_path / "watchdog"
    old_child, _ = _seed_overdue_lock(tmp_path, status_dir)
    fake_hermes = _make_fake_hermes(tmp_path)
    try:
        result = _run_watchdog(
            status_dir, fake_hermes, "--require-ao2-cancel-authority"
        )
        assert result.returncode == 2, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "refused"
        assert (
            payload["action"]
            == "refused_overdue_termination_pending_ao2_authority"
        )
        # legacy unilateral termination must NOT have happened
        assert payload.get("terminated_pid") is None
        assert old_child.poll() is None
        authority = payload.get("ao2_cancel_authority") or {}
        assert authority.get("decision") == "refuse_pending_ao2_authority_source"
        assert authority.get("mode") == "refused_no_source"
    finally:
        if old_child.poll() is None:
            old_child.terminate()
            old_child.wait(timeout=5)


def test_recover_overdue_with_invalid_cancel_transition_refuses_termination(
    tmp_path: Path,
) -> None:
    status_dir = tmp_path / "watchdog"
    old_child, _ = _seed_overdue_lock(tmp_path, status_dir)
    fake_hermes = _make_fake_hermes(tmp_path)
    bad_transition = tmp_path / "bad-transition.json"
    bad_transition.write_text(
        json.dumps(
            {
                "schema_version": TRANSITION_SCHEMA,
                # missing required fields → invalid
                "entry": {"status": "running"},
            }
        ),
        encoding="utf-8",
    )
    try:
        result = _run_watchdog(
            status_dir,
            fake_hermes,
            "--ao2-cancel-transition",
            str(bad_transition),
        )
        assert result.returncode == 2, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "refused"
        assert (
            payload["action"]
            == "refused_overdue_termination_invalid_ao2_authority"
        )
        # process must NOT have been terminated
        assert payload.get("terminated_pid") is None
        assert old_child.poll() is None
        authority = payload.get("ao2_cancel_authority") or {}
        assert authority.get("decision") == "refuse_invalid_ao2_authority_source"
        assert authority.get("error")  # blockers / validation message present
    finally:
        if old_child.poll() is None:
            old_child.terminate()
            old_child.wait(timeout=5)
