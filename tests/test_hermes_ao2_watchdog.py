from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hermes_ao2_watchdog.py"
PROMPT_FILE = ROOT / "run-artifacts" / "hermes-governed-backend-control-plane" / "prompt.txt"


def write_evidence_pack_fixture(
    target: Path,
    run_id: str,
    *,
    verdict: str,
    mtime: int,
    repair_source_run_id: str | None = None,
) -> Path:
    evidence_pack = target / ".ao2" / "runs" / run_id / "evidence-pack" / "evidence-pack.json"
    evidence_pack.parent.mkdir(parents=True)
    payload = {
        "schema_version": "ao2.evidence-pack.v1",
        "run_id": run_id,
        "verdict": verdict,
    }
    if repair_source_run_id is not None:
        payload["repair_source"] = {
            "schema_version": "ao2.repair-source.v1",
            "source_run_id": repair_source_run_id,
            "source_verdict": "rejected",
        }
    evidence_pack.write_text(json.dumps(payload), encoding="utf-8")
    os.utime(evidence_pack, (mtime, mtime))
    return evidence_pack


def test_hermes_ao2_watchdog_dry_run_writes_prompt_and_status(tmp_path: Path) -> None:
    status_dir = tmp_path / "watchdog"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--factory-root",
            str(ROOT),
            "--ao2-root",
            str(tmp_path / "ao2"),
            "--ao2-control-plane",
            str(ROOT.parent / "ao2-control-plane"),
            "--ao-runtime",
            str(ROOT.parent / "ao-runtime"),
            "--status-dir",
            str(status_dir),
            "--hermes-bin",
            "/usr/bin/false",
            "--dry-run",
            "--json",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["schema"] == "ao-operator/hermes-ao2-watchdog/v1"
    assert payload["status"] == "would_start"
    assert payload["next_check_seconds"] == 600
    assert payload["prompt"]["path"] == str(PROMPT_FILE)
    assert payload["prompt"]["sha256"]
    assert payload["prompt"]["snapshot_path"] == str(status_dir / "ao2-watchdog-prompt.md")
    assert payload["command"][0:2] == ["/usr/bin/false", "-z"]
    assert PROMPT_FILE.read_text(encoding="utf-8") in payload["command"][2]
    assert payload["backend_decision"]["mode"] == "normal_advancement"
    assert payload["command"][0] == "/usr/bin/false"
    assert (status_dir / "ao2-watchdog-prompt.md").is_file()
    snapshot = (status_dir / "ao2-watchdog-prompt.md").read_text(encoding="utf-8")
    assert PROMPT_FILE.read_text(encoding="utf-8") in snapshot
    assert "Backend route selected: normal_advancement" in snapshot
    saved = json.loads((status_dir / "watchdog-status.json").read_text(encoding="utf-8"))
    assert saved["status"] == "would_start"


def test_hermes_ao2_watchdog_dry_run_selects_repair_latest_when_rejected_evidence_exists(
    tmp_path: Path,
) -> None:
    status_dir = tmp_path / "watchdog"
    ao2_root = tmp_path / "ao2"
    write_evidence_pack_fixture(ao2_root, "accepted-run", verdict="accepted", mtime=300)
    write_evidence_pack_fixture(ao2_root, "older-rejected", verdict="rejected", mtime=100)
    latest_rejected = write_evidence_pack_fixture(
        ao2_root, "latest-rejected", verdict="rejected", mtime=200
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--factory-root",
            str(ROOT),
            "--ao2-root",
            str(ao2_root),
            "--ao2-control-plane",
            str(ROOT.parent / "ao2-control-plane"),
            "--ao-runtime",
            str(ROOT.parent / "ao-runtime"),
            "--status-dir",
            str(status_dir),
            "--hermes-bin",
            "/usr/bin/false",
            "--dry-run",
            "--json",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["backend_decision"]["mode"] == "repair_resume_latest"
    assert payload["backend_decision"]["selected"]["path"] == str(latest_rejected)
    backend_command = payload["backend_decision"]["command"]
    assert "repair-resume-latest" in backend_command
    assert backend_command[backend_command.index("--provider") + 1] == "codex"
    assert "--provider-prompt-file" in backend_command
    prompt_text = payload["command"][2]
    assert "Backend route selected: repair_resume_latest" in prompt_text
    assert str(latest_rejected) in prompt_text
    assert "repair-resume-latest" in prompt_text


def test_hermes_ao2_watchdog_dry_run_ignores_rejected_pack_with_newer_accepted_repair(
    tmp_path: Path,
) -> None:
    status_dir = tmp_path / "watchdog"
    ao2_root = tmp_path / "ao2"
    write_evidence_pack_fixture(ao2_root, "rejected-source", verdict="rejected", mtime=100)
    write_evidence_pack_fixture(
        ao2_root,
        "accepted-repair",
        verdict="accepted",
        mtime=200,
        repair_source_run_id="rejected-source",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--factory-root",
            str(ROOT),
            "--ao2-root",
            str(ao2_root),
            "--ao2-control-plane",
            str(ROOT.parent / "ao2-control-plane"),
            "--ao-runtime",
            str(ROOT.parent / "ao-runtime"),
            "--status-dir",
            str(status_dir),
            "--hermes-bin",
            "/usr/bin/false",
            "--dry-run",
            "--json",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["backend_decision"]["mode"] == "normal_advancement"
    assert payload["backend_decision"]["selected"] is None
    assert "repair-resume-latest" not in payload["command"][2]


def test_hermes_ao2_watchdog_writes_operator_panel_for_selected_backend_route(
    tmp_path: Path,
) -> None:
    status_dir = tmp_path / "watchdog"
    ao2_root = tmp_path / "ao2"
    latest_rejected = write_evidence_pack_fixture(
        ao2_root, "latest-rejected", verdict="rejected", mtime=200
    )

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--factory-root",
            str(ROOT),
            "--ao2-root",
            str(ao2_root),
            "--ao2-control-plane",
            str(ROOT.parent / "ao2-control-plane"),
            "--ao-runtime",
            str(ROOT.parent / "ao-runtime"),
            "--status-dir",
            str(status_dir),
            "--hermes-bin",
            "/usr/bin/false",
            "--dry-run",
            "--json",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    panel_json_path = status_dir / "watchdog-panel.json"
    panel_markdown_path = status_dir / "watchdog-panel.md"
    status_payload = json.loads((status_dir / "watchdog-status.json").read_text(encoding="utf-8"))
    history_json_path = Path(status_payload["artifacts"]["watchdog_panel_history_json"])
    history_markdown_path = Path(status_payload["artifacts"]["watchdog_panel_history_markdown"])
    panel = json.loads(panel_json_path.read_text(encoding="utf-8"))
    panel_markdown = panel_markdown_path.read_text(encoding="utf-8")

    assert status_payload["artifacts"]["watchdog_panel_json"] == str(panel_json_path)
    assert status_payload["artifacts"]["watchdog_panel_markdown"] == str(panel_markdown_path)
    assert panel["schema"] == "ao-operator/hermes-ao2-watchdog-panel/v1"
    assert panel["backend_route"] == "repair_resume_latest"
    assert panel["selected_evidence"]["path"] == str(latest_rejected)
    assert panel["operator_links"]["selected_evidence"] == str(latest_rejected)
    assert "repair-resume-latest" in panel["backend_command"]
    assert panel["trust_boundary"]["frontend"] == "Hermes"
    assert panel["trust_boundary"]["control_plane"] == "ao2-control-plane read-only observer"
    assert "# Hermes AO2 Watchdog Operator Panel" in panel_markdown
    assert "repair_resume_latest" in panel_markdown
    assert str(latest_rejected) in panel_markdown
    assert "ao2-control-plane read-only observer" in panel_markdown
    assert history_json_path.is_file()
    assert history_markdown_path.is_file()
    history_panel = json.loads(history_json_path.read_text(encoding="utf-8"))
    assert history_panel["backend_route"] == "repair_resume_latest"
    assert history_markdown_path.read_text(encoding="utf-8") == panel_markdown


def test_hermes_ao2_watchdog_publishes_panel_to_control_plane_from_token_env(
    tmp_path: Path,
) -> None:
    status_dir = tmp_path / "watchdog"
    ao2_root = tmp_path / "ao2"
    write_evidence_pack_fixture(ao2_root, "latest-rejected", verdict="rejected", mtime=200)
    captured: dict[str, object] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("content-length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            captured["post_path"] = self.path
            captured["authorization"] = self.headers.get("authorization")
            captured["body"] = json.loads(body)
            response = {
                "schema_version": "ao2.cp-ingest-receipt.v1",
                "sha256": "f" * 64,
                "ingested_schema_version": "ao-operator/hermes-ao2-watchdog-panel/v1",
            }
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))

        def do_GET(self) -> None:
            captured["get_path"] = self.path
            captured["get_authorization"] = self.headers.get("authorization")
            response = {
                "schema_version": "ao2.cp-hermes-watchdog-panel-latest.v1",
                "control_plane_role": "read-only-observer",
                "mutates_ao_artifacts": False,
                "control_plane_approves_release": False,
                "panel": {
                    "backend_route": "repair_resume_latest",
                    "selected_evidence": {"run_id": "latest-rejected"},
                },
                "links": {
                    "panel_html": "/api/v1/hermes/watchdog/panel",
                    "history_json": "/api/v1/hermes/watchdog/history.json",
                },
            }
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = dict(os.environ)
        env["AO2_CP_TEST_TOKEN"] = "cp-token"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--factory-root",
                str(ROOT),
                "--ao2-root",
                str(ao2_root),
                "--ao2-control-plane",
                str(ROOT.parent / "ao2-control-plane"),
                "--ao-runtime",
                str(ROOT.parent / "ao-runtime"),
                "--status-dir",
                str(status_dir),
                "--hermes-bin",
                "/usr/bin/false",
                "--publish-control-plane-url",
                f"http://127.0.0.1:{server.server_port}",
                "--publish-api-token-env",
                "AO2_CP_TEST_TOKEN",
                "--dry-run",
                "--json",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            env=env,
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    payload = json.loads(result.stdout)
    saved = json.loads((status_dir / "watchdog-status.json").read_text(encoding="utf-8"))
    for observed in (payload, saved):
        publish = observed["control_plane_publish"]
        assert publish["status"] == "published"
        assert publish["api_token_env"] == "AO2_CP_TEST_TOKEN"
        assert publish["receipt"]["sha256"] == "f" * 64
        assert publish["latest_snapshot"]["panel"]["backend_route"] == "repair_resume_latest"
        assert publish["observer_links"]["history_json"].endswith(
            "/api/v1/hermes/watchdog/history.json"
        )
        serialized = json.dumps(observed)
        assert "cp-token" not in serialized
        assert "Authorization" not in serialized
    assert captured["post_path"] == "/api/v1/hermes/watchdog/panel"
    assert captured["get_path"] == "/api/v1/hermes/watchdog/panel/latest.json"
    assert captured["authorization"] == "Bearer cp-token"
    assert captured["get_authorization"] == "Bearer cp-token"
    assert captured["body"]["schema"] == "ao-operator/hermes-ao2-watchdog-panel/v1"


def test_hermes_ao2_watchdog_skips_when_lock_pid_is_alive(tmp_path: Path) -> None:
    status_dir = tmp_path / "watchdog"
    lock_dir = status_dir / "ao2-watchdog.lock"
    lock_dir.mkdir(parents=True)
    (lock_dir / "pid").write_text(str(os.getpid()) + "\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--factory-root",
            str(ROOT),
            "--ao2-root",
            str(tmp_path / "ao2"),
            "--status-dir",
            str(status_dir),
            "--hermes-bin",
            "/usr/bin/false",
            "--json",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == "running"
    assert payload["active_pid"] == os.getpid()
    assert payload["action"] == "check_back_later"
    assert payload["next_check_seconds"] == 600
    assert payload["max_lock_age_seconds"] == 43200


def test_hermes_ao2_watchdog_reports_overdue_when_live_lock_is_too_old(tmp_path: Path) -> None:
    status_dir = tmp_path / "watchdog"
    lock_dir = status_dir / "ao2-watchdog.lock"
    lock_dir.mkdir(parents=True)
    (lock_dir / "pid").write_text(str(os.getpid()) + "\n", encoding="utf-8")
    old = time.time() - 120
    os.utime(lock_dir, (old, old))

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--factory-root",
            str(ROOT),
            "--ao2-root",
            str(tmp_path / "ao2"),
            "--status-dir",
            str(status_dir),
            "--hermes-bin",
            "/usr/bin/false",
            "--max-lock-age-minutes",
            "1",
            "--json",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == "overdue"
    assert payload["active_pid"] == os.getpid()
    assert payload["action"] == "running_past_max_lock_age"
    assert payload["lock_age_seconds"] >= 60
    assert payload["max_lock_age_seconds"] == 60


def test_hermes_ao2_watchdog_starts_background_hermes_job(tmp_path: Path) -> None:
    status_dir = tmp_path / "watchdog"
    marker = tmp_path / "started.json"
    fake_hermes = tmp_path / "hermes"
    fake_hermes.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "import os",
                "import json",
                "import sys",
                "import time",
                f"open({str(marker)!r}, 'w', encoding='utf-8').write(json.dumps({{'argv': sys.argv, 'env': dict(os.environ)}}))",
                "time.sleep(2)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fake_hermes.chmod(0o755)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--factory-root",
            str(ROOT),
            "--ao2-root",
            str(tmp_path / "ao2"),
            "--status-dir",
            str(status_dir),
            "--hermes-bin",
            str(fake_hermes),
            "--json",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == "started"
    assert payload["active_pid"] > 0
    assert payload["lock_dir"] == str(status_dir / "ao2-watchdog.lock")
    assert (status_dir / "ao2-watchdog.lock" / "pid").is_file()
    assert (status_dir / "logs").is_dir()
    for _ in range(20):
        if marker.is_file():
            break
        time.sleep(0.05)
    captured = json.loads(marker.read_text(encoding="utf-8"))
    assert captured["argv"][0:2] == [str(fake_hermes), "-z"]
    assert PROMPT_FILE.read_text(encoding="utf-8") in captured["argv"][2]
    assert "Backend route selected: normal_advancement" in captured["argv"][2]


def test_hermes_ao2_watchdog_recovers_overdue_live_job(tmp_path: Path) -> None:
    status_dir = tmp_path / "watchdog"
    lock_dir = status_dir / "ao2-watchdog.lock"
    lock_dir.mkdir(parents=True)
    old_child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    marker = tmp_path / "started.json"
    fake_hermes = tmp_path / "hermes"
    fake_hermes.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "import json",
                "import sys",
                "import time",
                f"open({str(marker)!r}, 'w', encoding='utf-8').write(json.dumps({{'argv': sys.argv}}))",
                "time.sleep(2)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fake_hermes.chmod(0o755)
    try:
        (lock_dir / "pid").write_text(str(old_child.pid) + "\n", encoding="utf-8")
        old = time.time() - 120
        os.utime(lock_dir, (old, old))

        result = subprocess.run(
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
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

        payload = json.loads(result.stdout)
        assert payload["status"] == "started"
        assert payload["action"] == "recovered_overdue_hermes_oneshot"
        assert payload["terminated_pid"] == old_child.pid
        assert payload["active_pid"] != old_child.pid
        for _ in range(20):
            if old_child.poll() is not None:
                break
            time.sleep(0.05)
        assert old_child.poll() is not None
        for _ in range(20):
            if marker.is_file():
                break
            time.sleep(0.05)
        assert marker.is_file()
    finally:
        if old_child.poll() is None:
            old_child.terminate()
            old_child.wait(timeout=5)


def test_hermes_ao2_watchdog_forwards_ao2_queue_ownership_flags_to_repair_resume_latest(
    tmp_path: Path,
) -> None:
    status_dir = tmp_path / "watchdog"
    ao2_root = tmp_path / "ao2"
    write_evidence_pack_fixture(
        ao2_root, "latest-rejected", verdict="rejected", mtime=200
    )
    submit = tmp_path / "queue-submit.json"
    submit.write_text("{}", encoding="utf-8")
    transition_a = tmp_path / "queue-retry-a.json"
    transition_a.write_text("{}", encoding="utf-8")
    transition_b = tmp_path / "queue-retry-b.json"
    transition_b.write_text("{}", encoding="utf-8")
    ownership_out = tmp_path / "ownership.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--factory-root",
            str(ROOT),
            "--ao2-root",
            str(ao2_root),
            "--ao2-control-plane",
            str(ROOT.parent / "ao2-control-plane"),
            "--ao-runtime",
            str(ROOT.parent / "ao-runtime"),
            "--status-dir",
            str(status_dir),
            "--hermes-bin",
            "/usr/bin/false",
            "--ao2-queue-submit",
            str(submit),
            "--ao2-queue-transition",
            str(transition_a),
            "--ao2-queue-transition",
            str(transition_b),
            "--ao2-queue-ownership-out",
            str(ownership_out),
            "--require-ao2-queue-ownership",
            "--dry-run",
            "--json",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    payload = json.loads(result.stdout)
    backend_command = payload["backend_decision"]["command"]
    assert "--ao2-queue-submit" in backend_command
    assert backend_command[backend_command.index("--ao2-queue-submit") + 1] == str(submit)
    transition_args = [
        backend_command[i + 1]
        for i, value in enumerate(backend_command)
        if value == "--ao2-queue-transition"
    ]
    assert transition_args == [str(transition_a), str(transition_b)]
    assert backend_command[backend_command.index("--ao2-queue-ownership-out") + 1] == str(
        ownership_out
    )
    assert "--require-ao2-queue-ownership" in backend_command
