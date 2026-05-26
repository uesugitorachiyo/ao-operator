from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ao2_factory_compat_nightly_run.py"

ORCHESTRATOR_SCHEMA = "ao-operator/ao2-factory-compat-nightly-run/v1"
AO2_PLAN_SCHEMA = "ao2.ao-operator-compat-plan-result.v1"
AO2_QUEUE_SUBMIT_SCHEMA = "ao2.ao-operator-compat-workbench-queue-submit.v1"
AO2_QUEUE_RUN_NEXT_SCHEMA = (
    "ao2.ao-operator-compat-workbench-queue-run-next.v1"
)
AO2_PACK_EVIDENCE_SCHEMA = "ao2.ao-operator-compat-pack-evidence.v1"
AO2_EVIDENCE_PACK_SCHEMA = "ao2.evidence-pack.v1"


def _seed_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "README.md").write_text("# fixture\n", encoding="utf-8")
    (fixture / "pyproject.toml").write_text("[project]\nname = 'fixture'\n", encoding="utf-8")
    sub = fixture / "fixture"
    sub.mkdir()
    (sub / "__init__.py").write_text("\n", encoding="utf-8")
    return fixture


def _empty_path_env() -> dict[str, str]:
    return {"PATH": ""}


def _fake_ao2_payloads(
    *,
    factory_target: Path,
    run_id: str,
    evidence_pack_out: Path,
    pack_status: str = "produced",
    pack_schema: str = AO2_PACK_EVIDENCE_SCHEMA,
    evidence_pack_schema: str = AO2_EVIDENCE_PACK_SCHEMA,
    signed: bool = False,
    signer_id: str = "ao2-factory-pack-evidence-signer",
    queue_run_next_entry_status: str = "accepted",
) -> dict[str, dict[str, Any]]:
    queue_path = factory_target / ".ao2" / "factory-compat" / "queue.json"
    return {
        "plan": {
            "schema_version": AO2_PLAN_SCHEMA,
            "evidence_path": str(
                factory_target / ".ao2" / "factory-compat" / "plan-evidence.json"
            ),
            "plan_path": str(
                factory_target / ".ao2" / "factory-compat" / "plan.json"
            ),
            "workflow_path": str(
                factory_target / ".ao2" / "factory-compat" / "workflow.json"
            ),
            "factory_v3_drives_workflow": False,
        },
        "queue-submit": {
            "schema_version": AO2_QUEUE_SUBMIT_SCHEMA,
            "status": "queued",
            "run_id": run_id,
            "queue_path": str(queue_path),
        },
        "queue-run-next": {
            "schema_version": AO2_QUEUE_RUN_NEXT_SCHEMA,
            "status": "accepted",
            "run_id": run_id,
            "entry": {
                "status": queue_run_next_entry_status,
                "native_evaluator_verdict": "accepted",
                "evidence_pack": str(
                    factory_target
                    / ".ao2"
                    / "factory-compat"
                    / f"{run_id}-evidence-pack.json"
                ),
                "run_result_path": str(
                    factory_target
                    / ".ao2"
                    / "factory-compat"
                    / f"{run_id}-result.json"
                ),
                "transition_history": [
                    {"status": "queued"},
                    {"status": "running"},
                    {"status": queue_run_next_entry_status},
                ],
            },
            "parity_checklist_progress": {
                "ao2_queue_can_execute_persisted_factory_compat_run": True,
                "factory_v3_drives_workflow": False,
            },
        },
        "pack-evidence": _pack_evidence_payload(
            run_id=run_id,
            evidence_pack_out=evidence_pack_out,
            status=pack_status,
            pack_schema=pack_schema,
            evidence_pack_schema=evidence_pack_schema,
            signed=signed,
            signer_id=signer_id,
        ),
    }


def _pack_evidence_payload(
    *,
    run_id: str,
    evidence_pack_out: Path,
    status: str,
    pack_schema: str,
    evidence_pack_schema: str,
    signed: bool,
    signer_id: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": pack_schema,
        "status": status,
        "run_id": run_id,
        "queue_path": "<fake>",
        "entry_status": "accepted",
        "native_evaluator_verdict": "accepted",
        "evidence_pack_source": "<fake-source>",
        "evidence_pack_source_sha256": "feedface",
        "evidence_pack_out": str(evidence_pack_out),
        "evidence_pack_sha256": "cafebabe",
        "evidence_pack_schema_version": evidence_pack_schema,
        "evidence_pack_execution_owner": "ao2",
        "factory_v3_role": "parity_oracle_only",
        "ao2_decision_owner": "ao2-workbench-queue",
        "control_plane_role": "read_only_observer_after_signed_evidence",
        "deterministic_replay": {
            "schema_version": (
                "ao2.ao-operator-compat-pack-evidence-deterministic-replay.v1"
            ),
            "verified": True,
            "replay_sha256": "cafebabe",
            "written_sha256": "cafebabe",
        },
        "signature": (
            {
                "schema_version": (
                    "ao2.ao-operator-compat-pack-evidence-signature.v1"
                ),
                "signed_payload": "evidence_pack_out",
                "signature_verified": False,
                "signature_status": "unsigned",
            }
            if not signed
            else {
                "schema_version": (
                    "ao2.ao-operator-compat-pack-evidence-signature.v1"
                ),
                "signature_algorithm": "RSA/SHA-256",
                "signer_id": signer_id,
                "signed_payload": "evidence_pack_out",
                "signed_payload_path": str(evidence_pack_out),
                "signed_payload_sha256": "cafebabe",
                "signature_path": str(evidence_pack_out) + ".sig",
                "signature_sha256": "feed",
                "public_key_path": str(evidence_pack_out) + ".public.pem",
                "public_key_sha256": "f00d",
                "signature_verified": True,
            }
        ),
    }
    return payload


def _write_fake_ao2(
    *,
    path: Path,
    payloads: dict[str, dict[str, Any]],
    evidence_pack_out: Path,
    pack_body: dict[str, Any] | None = None,
    write_pack_file: bool = True,
    fail_on: str | None = None,
    memory_payload: dict[str, Any] | None = None,
    memory_fail: bool = False,
) -> Path:
    """Materialise a Python ``ao2`` shim that routes by subcommand.

    The shim inspects ``argv[1:3]`` (e.g. ``factory plan``), looks up the
    matching payload, optionally writes a file (for ``pack-evidence``),
    and emits the payload as JSON. If ``fail_on`` matches the second
    positional argument, the shim exits non-zero so the orchestrator
    surfaces a ``failed`` status with the right stage.

    ``memory write`` is dispatched separately because it lives under a
    different top-level subcommand (``memory`` rather than ``factory``).
    When ``memory_payload`` is supplied the shim emits it; when
    ``memory_fail`` is true the shim exits non-zero so the orchestrator
    surfaces a ``memory-write`` failure stage.
    """

    if pack_body is None:
        pack_body = {
            "schema_version": AO2_EVIDENCE_PACK_SCHEMA,
            "runtime_contract": {
                "execution_owner": "ao2",
                "factory_v3_drives_workflow": False,
            },
            "workflow_tasks": [{"id": "intake"}],
        }

    payloads_json = json.dumps(payloads)
    pack_body_json = json.dumps(pack_body)
    memory_payload_json = json.dumps(memory_payload) if memory_payload is not None else "null"
    fail_repr = repr(fail_on)
    evidence_pack_out_repr = repr(str(evidence_pack_out))
    write_pack_flag = "True" if write_pack_file else "False"
    memory_fail_flag = "True" if memory_fail else "False"
    script = f"""#!{sys.executable}
import json
import os
import sys

PAYLOADS = json.loads({payloads_json!r})
PACK_BODY = json.loads({pack_body_json!r})
MEMORY_PAYLOAD = json.loads({memory_payload_json!r})
FAIL_ON = {fail_repr}
EVIDENCE_PACK_OUT = {evidence_pack_out_repr}
WRITE_PACK_FILE = {write_pack_flag}
MEMORY_FAIL = {memory_fail_flag}


def _flag_value(argv, name):
    for idx, token in enumerate(argv):
        if token == name and idx + 1 < len(argv):
            return argv[idx + 1]
    return None


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        sys.stderr.write("fake-ao2 missing subcommand\\n")
        return 2
    top = argv[0]
    if top == "memory":
        if len(argv) < 2 or argv[1] != "write":
            sys.stderr.write("fake-ao2 only handles `memory write` under memory\\n")
            return 2
        if MEMORY_FAIL:
            sys.stderr.write("fake-ao2 forced failure on memory write\\n")
            return 7
        if MEMORY_PAYLOAD is None:
            sys.stderr.write("fake-ao2 has no memory payload configured\\n")
            return 3
        # Echo arg-derived fields so tests can assert on them.
        record = dict(MEMORY_PAYLOAD)
        record.setdefault("kind", _flag_value(argv, "--kind"))
        record.setdefault("title", _flag_value(argv, "--title"))
        record.setdefault("body", _flag_value(argv, "--body"))
        record.setdefault(
            "source",
            {{
                "run_id": _flag_value(argv, "--source-run-id"),
                "path": _flag_value(argv, "--source-path"),
                "path_sha256": None,
            }},
        )
        sys.stdout.write(json.dumps(record))
        return 0
    if top != "factory":
        sys.stderr.write("fake-ao2 only handles `factory` or `memory` subcommands\\n")
        return 2
    if len(argv) < 2:
        sys.stderr.write("fake-ao2 missing factory subcommand\\n")
        return 2
    sub = argv[1]
    if FAIL_ON is not None and FAIL_ON == sub:
        sys.stderr.write(f"fake-ao2 forced failure on {{sub}}\\n")
        return 7
    payload = PAYLOADS.get(sub)
    if payload is None:
        sys.stderr.write(f"fake-ao2 has no payload for {{sub}}\\n")
        return 3
    if sub == "pack-evidence" and WRITE_PACK_FILE:
        os.makedirs(os.path.dirname(EVIDENCE_PACK_OUT), exist_ok=True)
        with open(EVIDENCE_PACK_OUT, "w", encoding="utf-8") as fh:
            json.dump(PACK_BODY, fh, indent=2, sort_keys=True)
            fh.write("\\n")
    sys.stdout.write(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def run_orchestrator(
    *,
    ao2_fixture: Path,
    target: Path,
    workdir: Path,
    evidence_pack_out: Path,
    write_json: Path,
    ao2_binary: str | None = None,
    run_id: str | None = None,
    signing_key: Path | None = None,
    signer_id: str | None = None,
    ao_operator_runspec: Path | None = None,
    bridge_evidence_out: Path | None = None,
    bridge_evidence_signing_key: Path | None = None,
    bridge_evidence_signer_id: str | None = None,
    hermes_context_out: Path | None = None,
    hermes_context_slug: str | None = None,
    control_plane_receipt: Path | None = None,
    memory_record_out: Path | None = None,
    memory_record_target: Path | None = None,
    memory_record_kind: str | None = None,
    memory_record_title: str | None = None,
    memory_record_body: str | None = None,
    require_all_ao2_ref_categories: bool = False,
    extra_env: dict[str, str] | None = None,
    expect_returncode: int = 0,
) -> tuple[dict | None, subprocess.CompletedProcess[str]]:
    args = [
        sys.executable,
        str(SCRIPT),
        "--ao2-fixture",
        str(ao2_fixture),
        "--target",
        str(target),
        "--workdir",
        str(workdir),
        "--evidence-pack-out",
        str(evidence_pack_out),
        "--write-json",
        str(write_json),
        "--json",
    ]
    if ao2_binary is not None:
        args.extend(["--ao2-binary", ao2_binary])
    if run_id is not None:
        args.extend(["--run-id", run_id])
    if signing_key is not None:
        args.extend(["--signing-key", str(signing_key)])
    if signer_id is not None:
        args.extend(["--signer-id", signer_id])
    if ao_operator_runspec is not None:
        args.extend(["--ao-operator-runspec", str(ao_operator_runspec)])
    if bridge_evidence_out is not None:
        args.extend(["--bridge-evidence-out", str(bridge_evidence_out)])
    if bridge_evidence_signing_key is not None:
        args.extend(
            ["--bridge-evidence-signing-key", str(bridge_evidence_signing_key)]
        )
    if bridge_evidence_signer_id is not None:
        args.extend(
            ["--bridge-evidence-signer-id", bridge_evidence_signer_id]
        )
    if hermes_context_out is not None:
        args.extend(["--hermes-context-out", str(hermes_context_out)])
    if hermes_context_slug is not None:
        args.extend(["--hermes-context-slug", hermes_context_slug])
    if control_plane_receipt is not None:
        args.extend(["--control-plane-receipt", str(control_plane_receipt)])
    if memory_record_out is not None:
        args.extend(["--memory-record-out", str(memory_record_out)])
    if memory_record_target is not None:
        args.extend(["--memory-record-target", str(memory_record_target)])
    if memory_record_kind is not None:
        args.extend(["--memory-record-kind", memory_record_kind])
    if memory_record_title is not None:
        args.extend(["--memory-record-title", memory_record_title])
    if memory_record_body is not None:
        args.extend(["--memory-record-body", memory_record_body])
    if require_all_ao2_ref_categories:
        args.append("--require-all-ao2-ref-categories")
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    assert result.returncode == expect_returncode, (
        f"unexpected exit {result.returncode}; stderr={result.stderr!r}"
    )
    if result.returncode != 0:
        return None, result
    payload = json.loads(result.stdout)
    on_disk = json.loads(write_json.read_text(encoding="utf-8"))
    assert payload == on_disk
    return payload, result


CANONICAL_AO_OPERATOR_RUNSPEC = """\
apiVersion: ao.dev/v1
kind: Run
metadata:
  name: nightly-bridge-smoke
  description: Bridge integration test runspec.
spec:
  tasks:
    - id: planner-intake
      kind: agent
      deps: []
      spec:
        provider: codex
    - id: plan-hardener
      kind: agent
      deps: ["planner-intake"]
      spec:
        provider: codex
    - id: factory-manager
      kind: agent
      deps: ["plan-hardener"]
      spec:
        provider: codex
    - id: implementer-slice
      kind: agent
      deps: ["factory-manager"]
      spec:
        provider: codex
    - id: reviewer-slice
      kind: agent
      deps: ["implementer-slice"]
      spec:
        provider: codex
    - id: integrator
      kind: agent
      deps: ["reviewer-slice"]
      spec:
        provider: codex
    - id: evaluator-closer
      kind: agent
      deps: ["integrator"]
      spec:
        provider: codex
"""


def _write_real_runspec(tmp_path: Path) -> Path:
    path = tmp_path / "ao-operator-runspec.yaml"
    path.write_text(CANONICAL_AO_OPERATOR_RUNSPEC, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# missing-inputs paths
# ---------------------------------------------------------------------------


def test_missing_inputs_when_binary_absent(tmp_path: Path) -> None:
    fixture = _seed_fixture(tmp_path)
    summary = tmp_path / "summary.json"
    target = tmp_path / "target"
    workdir = tmp_path / "workdir"
    out = tmp_path / "pack.json"

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=target,
        workdir=workdir,
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary="ao2-not-installed",
        extra_env=_empty_path_env(),
    )

    assert payload is not None
    assert payload["schema_version"] == ORCHESTRATOR_SCHEMA
    assert payload["status"] == "missing_inputs"
    assert payload["factory_v3_role"] == "parity_oracle_only"
    assert payload["ao2_decision_owner"] == "ao2-workbench-queue"
    assert (
        payload["control_plane_role"]
        == "read_only_observer_after_signed_evidence"
    )
    assert any(
        m.startswith("ao2_binary_not_on_path:ao2-not-installed")
        for m in payload["missing"]
    )
    # Target must NOT be materialised on a preflight failure.
    assert not target.exists()
    assert not out.exists()


def test_missing_inputs_when_fixture_not_directory(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    target = tmp_path / "target"
    workdir = tmp_path / "workdir"
    out = tmp_path / "pack.json"
    fake_ao2 = tmp_path / "ao2"
    _write_fake_ao2(
        path=fake_ao2,
        payloads={},
        evidence_pack_out=out,
    )

    payload, _ = run_orchestrator(
        ao2_fixture=tmp_path / "no-such-fixture",
        target=target,
        workdir=workdir,
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
    )

    assert payload is not None
    assert payload["status"] == "missing_inputs"
    assert any(
        m.startswith("ao2_fixture_not_a_directory:") for m in payload["missing"]
    )
    assert not target.exists()


def test_missing_inputs_when_signing_key_absent(tmp_path: Path) -> None:
    fixture = _seed_fixture(tmp_path)
    summary = tmp_path / "summary.json"
    target = tmp_path / "target"
    workdir = tmp_path / "workdir"
    out = tmp_path / "pack.json"
    fake_ao2 = tmp_path / "ao2"
    _write_fake_ao2(
        path=fake_ao2,
        payloads={},
        evidence_pack_out=out,
    )

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=target,
        workdir=workdir,
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        signing_key=tmp_path / "missing-key.pem",
        signer_id="ao2-test-signer",
    )

    assert payload is not None
    assert payload["status"] == "missing_inputs"
    assert any(m.startswith("signing_key_not_found:") for m in payload["missing"])
    assert not target.exists()


# ---------------------------------------------------------------------------
# produced path with fake ao2 binary
# ---------------------------------------------------------------------------


def test_produces_full_chain_with_fake_ao2_binary(tmp_path: Path) -> None:
    fixture = _seed_fixture(tmp_path)
    target = tmp_path / "target"
    workdir = tmp_path / "workdir"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    fake_ao2 = tmp_path / "ao2"
    run_id = "nightly-run-123"
    payloads = _fake_ao2_payloads(
        factory_target=target,
        run_id=run_id,
        evidence_pack_out=out,
    )
    _write_fake_ao2(
        path=fake_ao2,
        payloads=payloads,
        evidence_pack_out=out,
    )

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=target,
        workdir=workdir,
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        run_id=run_id,
    )

    assert payload is not None
    assert payload["schema_version"] == ORCHESTRATOR_SCHEMA
    assert payload["status"] == "produced"
    assert payload["stage"] == "complete"
    assert payload["factory_v3_role"] == "parity_oracle_only"
    assert payload["ao2_decision_owner"] == "ao2-workbench-queue"
    assert (
        payload["control_plane_role"]
        == "read_only_observer_after_signed_evidence"
    )
    assert payload["factory_target"] == str(target)
    assert payload["run_id"] == run_id
    assert payload["plan"]["schema_version"] == AO2_PLAN_SCHEMA
    assert payload["plan"]["factory_v3_drives_workflow"] is False
    assert payload["queue_submit"]["status"] == "queued"
    assert payload["queue_run_next"]["entry_status"] == "accepted"
    assert payload["queue_run_next"]["native_evaluator_verdict"] == "accepted"
    assert (
        payload["queue_run_next"]["parity_checklist_progress"][
            "ao2_queue_can_execute_persisted_factory_compat_run"
        ]
        is True
    )
    assert payload["pack_evidence_summary"]["schema_version"] == AO2_PACK_EVIDENCE_SCHEMA
    assert payload["evidence_pack_path"] == str(out)
    assert payload["evidence_pack_schema"] == AO2_EVIDENCE_PACK_SCHEMA
    assert payload["evidence_pack_signature"]["signature_status"] == "unsigned"
    assert payload["evidence_pack_deterministic_replay"]["verified"] is True
    # The orchestrator computes SHA-256 over the written pack independently.
    expected_sha = hashlib.sha256(out.read_bytes()).hexdigest()
    assert payload["evidence_pack_sha256"] == expected_sha
    # Target materialised; fixture file copied over.
    assert (target / "pyproject.toml").is_file()


def test_produces_signed_chain_when_signing_key_supplied(tmp_path: Path) -> None:
    fixture = _seed_fixture(tmp_path)
    target = tmp_path / "target"
    workdir = tmp_path / "workdir"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    fake_ao2 = tmp_path / "ao2"
    signing_key = tmp_path / "key.pem"
    signing_key.write_text("-----BEGIN FAKE KEY-----\n", encoding="utf-8")
    run_id = "signed-run"
    payloads = _fake_ao2_payloads(
        factory_target=target,
        run_id=run_id,
        evidence_pack_out=out,
        signed=True,
        signer_id="ao2-test-signer",
    )
    _write_fake_ao2(
        path=fake_ao2,
        payloads=payloads,
        evidence_pack_out=out,
    )

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=target,
        workdir=workdir,
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        run_id=run_id,
        signing_key=signing_key,
        signer_id="ao2-test-signer",
    )

    assert payload is not None
    assert payload["status"] == "produced"
    sig = payload["evidence_pack_signature"]
    assert sig["signature_verified"] is True
    assert sig["signer_id"] == "ao2-test-signer"
    assert payload["inputs"]["signing_key"] == str(signing_key)
    assert payload["inputs"]["signer_id"] == "ao2-test-signer"


# ---------------------------------------------------------------------------
# failure paths
# ---------------------------------------------------------------------------


def test_failure_when_pack_evidence_fails(tmp_path: Path) -> None:
    fixture = _seed_fixture(tmp_path)
    target = tmp_path / "target"
    workdir = tmp_path / "workdir"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    fake_ao2 = tmp_path / "ao2"
    run_id = "fail-pack-run"
    payloads = _fake_ao2_payloads(
        factory_target=target,
        run_id=run_id,
        evidence_pack_out=out,
    )
    _write_fake_ao2(
        path=fake_ao2,
        payloads=payloads,
        evidence_pack_out=out,
        fail_on="pack-evidence",
    )

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=target,
        workdir=workdir,
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        run_id=run_id,
    )

    assert payload is not None
    assert payload["status"] == "failed"
    assert payload["stage"] == "pack-evidence"
    assert "failed" in payload["failure_reason"]
    # Partial state captures the upstream stage success.
    assert payload["partial"]["queue_run_next"]["entry"]["status"] == "accepted"
    assert payload["evidence_pack_path"] is None


def test_failure_when_queue_run_next_does_not_accept(tmp_path: Path) -> None:
    fixture = _seed_fixture(tmp_path)
    target = tmp_path / "target"
    workdir = tmp_path / "workdir"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    fake_ao2 = tmp_path / "ao2"
    run_id = "rejected-run"
    payloads = _fake_ao2_payloads(
        factory_target=target,
        run_id=run_id,
        evidence_pack_out=out,
        queue_run_next_entry_status="rejected",
    )
    _write_fake_ao2(
        path=fake_ao2,
        payloads=payloads,
        evidence_pack_out=out,
    )

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=target,
        workdir=workdir,
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        run_id=run_id,
    )

    assert payload is not None
    assert payload["status"] == "failed"
    assert payload["stage"] == "queue-run-next"
    assert "expected 'accepted'" in payload["failure_reason"]


def test_signer_id_requires_signing_key(tmp_path: Path) -> None:
    fixture = _seed_fixture(tmp_path)
    target = tmp_path / "target"
    workdir = tmp_path / "workdir"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    fake_ao2 = tmp_path / "ao2"
    _write_fake_ao2(
        path=fake_ao2,
        payloads={},
        evidence_pack_out=out,
    )

    payload, result = run_orchestrator(
        ao2_fixture=fixture,
        target=target,
        workdir=workdir,
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        signer_id="ao2-bad",
        expect_returncode=1,
    )

    assert payload is None
    assert "--signer-id requires --signing-key" in result.stderr


# ---------------------------------------------------------------------------
# AO Operator -> AO2 bridge + Hermes AO2-refs context wiring
# ---------------------------------------------------------------------------


def test_ao_operator_runspec_requires_bridge_evidence_out(tmp_path: Path) -> None:
    """--ao-operator-runspec without --bridge-evidence-out fails fast."""
    fixture = _seed_fixture(tmp_path)
    runspec = _write_real_runspec(tmp_path)
    fake_ao2 = tmp_path / "ao2"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    _write_fake_ao2(path=fake_ao2, payloads={}, evidence_pack_out=out)

    payload, result = run_orchestrator(
        ao2_fixture=fixture,
        target=tmp_path / "target",
        workdir=tmp_path / "workdir",
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        ao_operator_runspec=runspec,
        expect_returncode=1,
    )

    assert payload is None
    assert "--bridge-evidence-out" in result.stderr


def test_bridge_evidence_out_requires_ao_operator_runspec(tmp_path: Path) -> None:
    """--bridge-evidence-out without --ao-operator-runspec fails fast."""
    fixture = _seed_fixture(tmp_path)
    fake_ao2 = tmp_path / "ao2"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    _write_fake_ao2(path=fake_ao2, payloads={}, evidence_pack_out=out)

    payload, result = run_orchestrator(
        ao2_fixture=fixture,
        target=tmp_path / "target",
        workdir=tmp_path / "workdir",
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        bridge_evidence_out=tmp_path / "bridge.json",
        expect_returncode=1,
    )

    assert payload is None
    assert "--ao-operator-runspec" in result.stderr


def test_missing_ao_operator_runspec_surfaces_in_missing_inputs(tmp_path: Path) -> None:
    """A non-existent --ao-operator-runspec path is reported as missing_inputs."""
    fixture = _seed_fixture(tmp_path)
    fake_ao2 = tmp_path / "ao2"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    bridge_out = tmp_path / "bridge.json"
    _write_fake_ao2(path=fake_ao2, payloads={}, evidence_pack_out=out)

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=tmp_path / "target",
        workdir=tmp_path / "workdir",
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        ao_operator_runspec=tmp_path / "no-such.yaml",
        bridge_evidence_out=bridge_out,
    )

    assert payload is not None
    assert payload["status"] == "missing_inputs"
    assert any(
        m.startswith("ao_operator_runspec_not_found:") for m in payload["missing"]
    )
    # bridge evidence must not have been written for missing inputs.
    assert not bridge_out.exists()


def test_produces_chain_with_real_runspec_bridge_and_hermes_context(
    tmp_path: Path,
) -> None:
    """End-to-end: real RunSpec drives bridge, Hermes context pins AO2 IDs.

    Phase 2 exit-gate items #1 (RunSpec -> bridge), #2 (deterministic mapping
    exercised), and #3 (Hermes context references AO2-owned IDs) all
    travel through the orchestrator on this path.
    """
    fixture = _seed_fixture(tmp_path)
    target = tmp_path / "target"
    workdir = tmp_path / "workdir"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    bridge_out = tmp_path / "bridge-evidence.json"
    hermes_out = tmp_path / "hermes-context.json"
    fake_ao2 = tmp_path / "ao2"
    runspec = _write_real_runspec(tmp_path)
    run_id = "nightly-bridge-run"

    payloads = _fake_ao2_payloads(
        factory_target=target,
        run_id=run_id,
        evidence_pack_out=out,
    )
    # Make the AO2 evidence pack body include a run_id + closure_status so
    # the AO2-refs helper pulls real values, not None.
    pack_body = {
        "schema_version": AO2_EVIDENCE_PACK_SCHEMA,
        "run_id": run_id,
        "ticket_id": run_id,
        "closure_status": "closed",
        "runtime_contract": {
            "execution_owner": "ao2",
            "factory_v3_drives_workflow": False,
        },
        "workflow_tasks": [{"id": "intake"}],
    }
    _write_fake_ao2(
        path=fake_ao2,
        payloads=payloads,
        evidence_pack_out=out,
        pack_body=pack_body,
    )

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=target,
        workdir=workdir,
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        run_id=run_id,
        ao_operator_runspec=runspec,
        bridge_evidence_out=bridge_out,
        hermes_context_out=hermes_out,
        hermes_context_slug=run_id,
    )

    assert payload is not None
    assert payload["status"] == "produced"

    # bridge evidence summary surfaced in the produced payload.
    bridge_summary = payload["bridge_evidence"]
    assert bridge_summary is not None
    assert bridge_summary["schema"] == (
        "ao-operator/start-ao2-run-from-role-runspec/v1"
    )
    assert bridge_summary["status"] == "mapping_resolved_dry_run"
    assert bridge_summary["unknown_role_count"] == 0
    assert bridge_summary["resolved_role_count"] == 7
    assert bridge_summary["mapping_digest"]
    # bridge evidence file written and matches the summarised digest.
    assert bridge_out.is_file()
    bridge_evidence = json.loads(bridge_out.read_text(encoding="utf-8"))
    assert (
        bridge_evidence["mapping"]["digest"]
        == bridge_summary["mapping_digest"]
    )
    assert bridge_evidence["status"] == "mapping_resolved_dry_run"
    # The RunSpec id is what the bridge canonicalises against; tasks resolve
    # to the canonical AO2 contract slugs.
    resolved_role_ids = sorted(
        r["role_id"] for r in bridge_evidence["resolved_roles"]
    )
    assert resolved_role_ids == [
        "evaluator-closer",
        "factory-manager",
        "implementer-slice",
        "integrator",
        "plan-hardener",
        "planner-intake",
        "reviewer-slice",
    ]

    # Hermes context summary surfaced + on-disk payload references AO2 IDs.
    hermes_summary = payload["hermes_context_with_ao2_refs"]
    assert hermes_summary is not None
    assert hermes_summary["schema"] == (
        "ao-operator/hermes-context-with-ao2-refs/v1"
    )
    assert hermes_summary["slug"] == run_id
    assert hermes_summary["factory_v3_local_paths_omitted"] is True
    assert hermes_summary["ao2_provider_contract_mapping_digest"] == (
        bridge_summary["mapping_digest"]
    )
    assert hermes_summary["ao2_evidence_pack_sha256"]
    assert hermes_summary["ao2_run_id"] == run_id
    assert hermes_summary["ao2_closure_status"] == "closed"
    assert hermes_out.is_file()
    hermes_payload = json.loads(hermes_out.read_text(encoding="utf-8"))
    assert hermes_payload["schema"] == (
        "ao-operator/hermes-context-with-ao2-refs/v1"
    )
    assert hermes_payload["factory_v3_local_paths_omitted"] is True
    assert (
        hermes_payload["ao2_refs"]["ao2_provider_contract_mapping_digest"]
        == bridge_summary["mapping_digest"]
    )
    assert hermes_payload["ao2_refs"]["ao2_run_id"] == run_id
    # The orchestrator independently computes the AO2 evidence-pack sha256
    # and pins it into the Hermes context payload.
    expected_pack_sha = hashlib.sha256(out.read_bytes()).hexdigest()
    assert (
        hermes_payload["ao2_refs"]["ao2_evidence_pack_sha256"]
        == expected_pack_sha
    )
    # inputs block exposes the new flag values.
    assert payload["inputs"]["ao_operator_runspec"] == str(runspec)
    assert payload["inputs"]["bridge_evidence_out"] == str(bridge_out)
    assert payload["inputs"]["hermes_context_out"] == str(hermes_out)
    assert payload["inputs"]["hermes_context_slug"] == run_id


def test_failed_payload_carries_bridge_evidence_summary(tmp_path: Path) -> None:
    """Bridge evidence summary is preserved when a downstream AO2 stage fails."""
    fixture = _seed_fixture(tmp_path)
    target = tmp_path / "target"
    workdir = tmp_path / "workdir"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    bridge_out = tmp_path / "bridge-evidence.json"
    fake_ao2 = tmp_path / "ao2"
    runspec = _write_real_runspec(tmp_path)
    run_id = "bridge-then-fail"

    payloads = _fake_ao2_payloads(
        factory_target=target,
        run_id=run_id,
        evidence_pack_out=out,
    )
    _write_fake_ao2(
        path=fake_ao2,
        payloads=payloads,
        evidence_pack_out=out,
        fail_on="plan",
    )

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=target,
        workdir=workdir,
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        run_id=run_id,
        ao_operator_runspec=runspec,
        bridge_evidence_out=bridge_out,
    )

    assert payload is not None
    assert payload["status"] == "failed"
    assert payload["stage"] == "plan"
    # Bridge ran before AO2 plan failed; the summary must still travel.
    assert payload["bridge_evidence"] is not None
    assert payload["bridge_evidence"]["resolved_role_count"] == 7
    # No Hermes context for a failed run (evidence pack was never produced).
    assert payload["hermes_context_with_ao2_refs"] is None


def test_control_plane_receipt_requires_hermes_context_out(tmp_path: Path) -> None:
    """--control-plane-receipt without --hermes-context-out fails fast."""
    fixture = _seed_fixture(tmp_path)
    fake_ao2 = tmp_path / "ao2"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "schema_version": "ao2.cp-ingest-receipt.v1",
                "sha256": "deadbeef",
                "stored_at": "2026-05-25T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    _write_fake_ao2(path=fake_ao2, payloads={}, evidence_pack_out=out)

    payload, result = run_orchestrator(
        ao2_fixture=fixture,
        target=tmp_path / "target",
        workdir=tmp_path / "workdir",
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        control_plane_receipt=receipt,
        expect_returncode=1,
    )

    assert payload is None
    assert "--hermes-context-out" in result.stderr


def test_missing_control_plane_receipt_surfaces_in_missing_inputs(
    tmp_path: Path,
) -> None:
    """Non-existent --control-plane-receipt is reported as missing_inputs."""
    fixture = _seed_fixture(tmp_path)
    fake_ao2 = tmp_path / "ao2"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    hermes_out = tmp_path / "hermes-context.json"
    _write_fake_ao2(path=fake_ao2, payloads={}, evidence_pack_out=out)

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=tmp_path / "target",
        workdir=tmp_path / "workdir",
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        hermes_context_out=hermes_out,
        control_plane_receipt=tmp_path / "no-such-receipt.json",
    )

    assert payload is not None
    assert payload["status"] == "missing_inputs"
    assert any(
        m.startswith("control_plane_receipt_not_found:")
        for m in payload["missing"]
    )


def test_hermes_context_pins_control_plane_receipt(tmp_path: Path) -> None:
    """When --control-plane-receipt is supplied, the Hermes context pins it."""
    fixture = _seed_fixture(tmp_path)
    target = tmp_path / "target"
    workdir = tmp_path / "workdir"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    hermes_out = tmp_path / "hermes-context.json"
    bridge_out = tmp_path / "bridge-evidence.json"
    fake_ao2 = tmp_path / "ao2"
    runspec = _write_real_runspec(tmp_path)
    run_id = "cp-receipt-pinned"

    receipt_path = tmp_path / "cp-ingest-receipt.json"
    receipt_value = {
        "schema_version": "ao2.cp-ingest-receipt.v1",
        "sha256": "9f3e1a2b3c4d5e6f7890abcdef1234567890abcdef1234567890abcdef123456",
        "stored_at": "2026-05-25T02:00:00Z",
        "ingested_schema_version": "ao2.evidence-pack.v1",
    }
    receipt_path.write_text(json.dumps(receipt_value), encoding="utf-8")

    payloads = _fake_ao2_payloads(
        factory_target=target,
        run_id=run_id,
        evidence_pack_out=out,
    )
    pack_body = {
        "schema_version": AO2_EVIDENCE_PACK_SCHEMA,
        "run_id": run_id,
        "closure_status": "closed",
    }
    _write_fake_ao2(
        path=fake_ao2,
        payloads=payloads,
        evidence_pack_out=out,
        pack_body=pack_body,
    )

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=target,
        workdir=workdir,
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        run_id=run_id,
        ao_operator_runspec=runspec,
        bridge_evidence_out=bridge_out,
        hermes_context_out=hermes_out,
        hermes_context_slug=run_id,
        control_plane_receipt=receipt_path,
    )

    assert payload is not None
    assert payload["status"] == "produced"
    # inputs block carries the receipt path.
    assert payload["inputs"]["control_plane_receipt"] == str(receipt_path)
    # Hermes summary pulls the receipt sha + stored_at + ingested schema.
    hermes_summary = payload["hermes_context_with_ao2_refs"]
    assert hermes_summary["control_plane_ingest_sha256"] == receipt_value["sha256"]
    assert hermes_summary["control_plane_stored_at"] == receipt_value["stored_at"]
    assert (
        hermes_summary["control_plane_ingested_schema_version"]
        == receipt_value["ingested_schema_version"]
    )
    # On-disk Hermes payload pins the same receipt fields.
    hermes_payload = json.loads(hermes_out.read_text(encoding="utf-8"))
    refs = hermes_payload["ao2_refs"]
    assert refs["control_plane_ingest_sha256"] == receipt_value["sha256"]
    assert refs["control_plane_stored_at"] == receipt_value["stored_at"]
    assert (
        refs["control_plane_ingested_schema_version"]
        == receipt_value["ingested_schema_version"]
    )


def test_bridge_blocks_when_runspec_has_unknown_role(tmp_path: Path) -> None:
    """Unknown role IDs fail at the bridge stage before any AO2 invocation."""
    fixture = _seed_fixture(tmp_path)
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    bridge_out = tmp_path / "bridge-evidence.json"
    fake_ao2 = tmp_path / "ao2"
    _write_fake_ao2(path=fake_ao2, payloads={}, evidence_pack_out=out)
    bad_runspec = tmp_path / "bad-runspec.yaml"
    bad_runspec.write_text(
        "apiVersion: ao.dev/v1\n"
        "kind: Run\n"
        "metadata:\n"
        "  name: bad-runspec\n"
        "spec:\n"
        "  tasks:\n"
        "    - id: not-a-real-role\n"
        "      kind: agent\n"
        "      spec:\n"
        "        provider: codex\n",
        encoding="utf-8",
    )

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=tmp_path / "target",
        workdir=tmp_path / "workdir",
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        ao_operator_runspec=bad_runspec,
        bridge_evidence_out=bridge_out,
    )

    assert payload is not None
    assert payload["status"] == "failed"
    assert payload["stage"] == "bridge-canonicalize"
    assert "not-a-real-role" in payload["failure_reason"]
    # No bridge evidence written when the bridge itself refused the input.
    assert not bridge_out.exists()


# ---------------------------------------------------------------------------
# AO2 memory record id wiring (Phase 2 exit-gate item #3, memory half)
# ---------------------------------------------------------------------------


def _fake_memory_payload(record_id: str = "mem-test-1") -> dict[str, Any]:
    return {
        "schema_version": "ao2.memory-record.v1",
        "id": record_id,
        "created_at_ms": 1778685620993228000,
    }


def test_memory_record_out_requires_hermes_context_out(tmp_path: Path) -> None:
    """--memory-record-out without --hermes-context-out fails fast."""
    fixture = _seed_fixture(tmp_path)
    fake_ao2 = tmp_path / "ao2"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    record_out = tmp_path / "memory-record.json"
    _write_fake_ao2(path=fake_ao2, payloads={}, evidence_pack_out=out)

    payload, result = run_orchestrator(
        ao2_fixture=fixture,
        target=tmp_path / "target",
        workdir=tmp_path / "workdir",
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        memory_record_out=record_out,
        expect_returncode=1,
    )

    assert payload is None
    assert "--hermes-context-out" in result.stderr
    assert "memory record id" in result.stderr or "memory-record-out" in result.stderr


def test_memory_record_options_require_out_path(tmp_path: Path) -> None:
    """--memory-record-title without --memory-record-out fails fast."""
    fixture = _seed_fixture(tmp_path)
    fake_ao2 = tmp_path / "ao2"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    _write_fake_ao2(path=fake_ao2, payloads={}, evidence_pack_out=out)

    payload, result = run_orchestrator(
        ao2_fixture=fixture,
        target=tmp_path / "target",
        workdir=tmp_path / "workdir",
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        hermes_context_out=tmp_path / "hermes-context.json",
        memory_record_title="custom title",
        expect_returncode=1,
    )

    assert payload is None
    assert "--memory-record-out" in result.stderr


def test_memory_write_failure_surfaces_failed_stage(tmp_path: Path) -> None:
    """When ao2 memory write fails the orchestrator stops with failed stage."""
    fixture = _seed_fixture(tmp_path)
    target = tmp_path / "target"
    workdir = tmp_path / "workdir"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    hermes_out = tmp_path / "hermes-context.json"
    bridge_out = tmp_path / "bridge-evidence.json"
    record_out = tmp_path / "memory-record.json"
    fake_ao2 = tmp_path / "ao2"
    runspec = _write_real_runspec(tmp_path)
    run_id = "memory-write-fail"

    payloads = _fake_ao2_payloads(
        factory_target=target,
        run_id=run_id,
        evidence_pack_out=out,
    )
    _write_fake_ao2(
        path=fake_ao2,
        payloads=payloads,
        evidence_pack_out=out,
        memory_payload=_fake_memory_payload(record_id=f"mem-{run_id}-1"),
        memory_fail=True,
    )

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=target,
        workdir=workdir,
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        run_id=run_id,
        ao_operator_runspec=runspec,
        bridge_evidence_out=bridge_out,
        hermes_context_out=hermes_out,
        memory_record_out=record_out,
    )

    assert payload is not None
    assert payload["status"] == "failed"
    assert payload["stage"] == "memory-write"
    # Hermes context never written when the memory step failed before it.
    assert not hermes_out.exists()
    assert not record_out.exists()
    # Bridge evidence still travels in failed payloads.
    assert payload["bridge_evidence"] is not None
    assert payload["memory_record"] is None


def test_hermes_context_pins_memory_record(tmp_path: Path) -> None:
    """When --memory-record-out is supplied, the Hermes context pins the record id + sha256."""
    fixture = _seed_fixture(tmp_path)
    target = tmp_path / "target"
    workdir = tmp_path / "workdir"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    hermes_out = tmp_path / "hermes-context.json"
    bridge_out = tmp_path / "bridge-evidence.json"
    record_out = tmp_path / "memory-record.json"
    fake_ao2 = tmp_path / "ao2"
    runspec = _write_real_runspec(tmp_path)
    run_id = "memory-pinned"

    payloads = _fake_ao2_payloads(
        factory_target=target,
        run_id=run_id,
        evidence_pack_out=out,
    )
    pack_body = {
        "schema_version": AO2_EVIDENCE_PACK_SCHEMA,
        "run_id": run_id,
        "closure_status": "closed",
    }
    record_id = f"mem-{run_id}-deadbeefcafe"
    _write_fake_ao2(
        path=fake_ao2,
        payloads=payloads,
        evidence_pack_out=out,
        pack_body=pack_body,
        memory_payload=_fake_memory_payload(record_id=record_id),
    )

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=target,
        workdir=workdir,
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        run_id=run_id,
        ao_operator_runspec=runspec,
        bridge_evidence_out=bridge_out,
        hermes_context_out=hermes_out,
        hermes_context_slug=run_id,
        memory_record_out=record_out,
    )

    assert payload is not None
    assert payload["status"] == "produced"

    # The orchestrator captured the input wiring in the summary block.
    assert payload["inputs"]["memory_record_out"] == str(record_out)
    assert payload["inputs"]["memory_record_target"] == str(target)
    assert payload["inputs"]["memory_record_kind"] == "ao-operator-compat-nightly-run"

    # Per-record summary block is populated with AO2-owned fields.
    record_summary = payload["memory_record"]
    assert record_summary is not None
    assert record_summary["schema_version"] == "ao2.memory-record.v1"
    assert record_summary["memory_record_id"] == record_id
    assert record_summary["memory_record_path"] == str(record_out)
    assert record_summary["source_run_id"] == run_id
    assert record_summary["kind"] == "ao-operator-compat-nightly-run"
    assert record_summary["title"] == f"AO2 nightly factory-compat run {run_id}"

    # The record JSON written to disk matches the orchestrator-computed sha256.
    expected_record_sha = hashlib.sha256(
        record_out.read_bytes()
    ).hexdigest()
    assert record_summary["memory_record_sha256"] == expected_record_sha

    # Hermes context summary surfaces the record id + sha + schema.
    hermes_summary = payload["hermes_context_with_ao2_refs"]
    assert hermes_summary["ao2_memory_record_id"] == record_id
    assert hermes_summary["ao2_memory_record_sha256"] == expected_record_sha
    assert hermes_summary["ao2_memory_record_schema"] == "ao2.memory-record.v1"
    assert "ao2_memory_record_id" in hermes_summary["ao2_ref_keys"]

    # On-disk Hermes context payload carries the same identifiers.
    context = json.loads(hermes_out.read_text(encoding="utf-8"))
    refs = context["ao2_refs"]
    assert refs["ao2_memory_record_id"] == record_id
    assert refs["ao2_memory_record_sha256"] == expected_record_sha
    assert refs["ao2_memory_record_schema"] == "ao2.memory-record.v1"
    # All four AO2 identifier families now ride in the payload.
    assert "ao2_provider_contract_mapping_digest" in refs
    assert "ao2_evidence_pack_sha256" in refs
    assert "ao2_run_id" in refs


def test_hermes_context_pins_memory_record_with_custom_body(tmp_path: Path) -> None:
    """Custom --memory-record-body overrides the default body string."""
    fixture = _seed_fixture(tmp_path)
    target = tmp_path / "target"
    workdir = tmp_path / "workdir"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    hermes_out = tmp_path / "hermes-context.json"
    bridge_out = tmp_path / "bridge-evidence.json"
    record_out = tmp_path / "memory-record.json"
    fake_ao2 = tmp_path / "ao2"
    runspec = _write_real_runspec(tmp_path)
    run_id = "memory-custom-body"

    payloads = _fake_ao2_payloads(
        factory_target=target,
        run_id=run_id,
        evidence_pack_out=out,
    )
    _write_fake_ao2(
        path=fake_ao2,
        payloads=payloads,
        evidence_pack_out=out,
        memory_payload=_fake_memory_payload(record_id=f"mem-{run_id}-1"),
    )

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=target,
        workdir=workdir,
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        run_id=run_id,
        ao_operator_runspec=runspec,
        bridge_evidence_out=bridge_out,
        hermes_context_out=hermes_out,
        memory_record_out=record_out,
        memory_record_kind="custom-kind",
        memory_record_title="custom title",
        memory_record_body="custom body line",
    )

    assert payload is not None
    assert payload["status"] == "produced"
    assert payload["inputs"]["memory_record_kind"] == "custom-kind"
    assert payload["inputs"]["memory_record_title"] == "custom title"
    assert payload["inputs"]["memory_record_body"] == "custom body line"

    # The fake ao2 shim echoes --kind/--title/--body into the record so
    # the orchestrator's downstream summary reflects those overrides.
    record_on_disk = json.loads(record_out.read_text(encoding="utf-8"))
    assert record_on_disk["kind"] == "custom-kind"
    assert record_on_disk["title"] == "custom title"
    assert record_on_disk["body"] == "custom body line"
    assert record_on_disk["source"]["run_id"] == run_id


def test_hermes_context_pins_memory_record_and_cp_receipt_together(tmp_path: Path) -> None:
    """All four AO2 identifier families coexist in the Hermes payload."""
    fixture = _seed_fixture(tmp_path)
    target = tmp_path / "target"
    workdir = tmp_path / "workdir"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    hermes_out = tmp_path / "hermes-context.json"
    bridge_out = tmp_path / "bridge-evidence.json"
    record_out = tmp_path / "memory-record.json"
    fake_ao2 = tmp_path / "ao2"
    runspec = _write_real_runspec(tmp_path)
    run_id = "memory-and-cp-receipt"

    receipt_path = tmp_path / "cp-ingest-receipt.json"
    receipt_value = {
        "schema_version": "ao2.cp-ingest-receipt.v1",
        "sha256": "9f3e1a2b3c4d5e6f7890abcdef1234567890abcdef1234567890abcdef123456",
        "stored_at": "2026-05-25T03:00:00Z",
        "ingested_schema_version": "ao2.evidence-pack.v1",
    }
    receipt_path.write_text(json.dumps(receipt_value), encoding="utf-8")

    payloads = _fake_ao2_payloads(
        factory_target=target,
        run_id=run_id,
        evidence_pack_out=out,
    )
    pack_body = {
        "schema_version": AO2_EVIDENCE_PACK_SCHEMA,
        "run_id": run_id,
        "closure_status": "closed",
    }
    record_id = f"mem-{run_id}-1"
    _write_fake_ao2(
        path=fake_ao2,
        payloads=payloads,
        evidence_pack_out=out,
        pack_body=pack_body,
        memory_payload=_fake_memory_payload(record_id=record_id),
    )

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=target,
        workdir=workdir,
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        run_id=run_id,
        ao_operator_runspec=runspec,
        bridge_evidence_out=bridge_out,
        hermes_context_out=hermes_out,
        hermes_context_slug=run_id,
        control_plane_receipt=receipt_path,
        memory_record_out=record_out,
    )

    assert payload is not None
    assert payload["status"] == "produced"

    context = json.loads(hermes_out.read_text(encoding="utf-8"))
    refs = context["ao2_refs"]
    # All four AO2 identifier families pinned in one payload.
    assert refs["ao2_provider_contract_mapping_digest"]
    assert refs["ao2_evidence_pack_sha256"]
    assert refs["ao2_run_id"] == run_id
    assert refs["ao2_memory_record_id"] == record_id
    assert refs["control_plane_ingest_sha256"] == receipt_value["sha256"]


# ---------------------------------------------------------------------------
# Phase 2 exit-gate #4: AO2-native bridge-evidence signing (slice 14)
#
# Slice 14 replaces the optional Python-helper bridge canonicalization with a
# shell-out to ``ao2 factory bridge --signing-key`` when the operator supplies
# an AO2-owned signing key. Default behaviour stays on the Python helper so
# the legacy schema ``ao-operator/start-ao2-run-from-role-runspec/v1`` continues
# to be emitted when no key is supplied; the new code path emits the AO2-native
# schema ``ao2.factory-bridge.v1`` plus signed sidecars that downstream
# consumers (and ao-operator's own slice-12 default-on passthrough verifier)
# can verify end-to-end.
# ---------------------------------------------------------------------------


def test_bridge_evidence_signing_key_requires_ao_operator_runspec(
    tmp_path: Path,
) -> None:
    """--bridge-evidence-signing-key requires --ao-operator-runspec."""
    fixture = _seed_fixture(tmp_path)
    fake_ao2 = tmp_path / "ao2"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    key = tmp_path / "signing-key.pem"
    key.write_text("-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n", encoding="utf-8")
    _write_fake_ao2(path=fake_ao2, payloads={}, evidence_pack_out=out)

    payload, result = run_orchestrator(
        ao2_fixture=fixture,
        target=tmp_path / "target",
        workdir=tmp_path / "workdir",
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        bridge_evidence_signing_key=key,
        expect_returncode=1,
    )

    assert payload is None
    assert "--bridge-evidence-signing-key" in result.stderr
    assert "--ao-operator-runspec" in result.stderr


def test_bridge_evidence_signing_key_requires_bridge_evidence_out(
    tmp_path: Path,
) -> None:
    """--bridge-evidence-signing-key requires --bridge-evidence-out.

    Without an output path the orchestrator has nowhere to write the AO2-native
    signed evidence + sidecars.
    """
    fixture = _seed_fixture(tmp_path)
    runspec = _write_real_runspec(tmp_path)
    fake_ao2 = tmp_path / "ao2"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    key = tmp_path / "signing-key.pem"
    key.write_text("-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n", encoding="utf-8")
    _write_fake_ao2(path=fake_ao2, payloads={}, evidence_pack_out=out)

    payload, result = run_orchestrator(
        ao2_fixture=fixture,
        target=tmp_path / "target",
        workdir=tmp_path / "workdir",
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        ao_operator_runspec=runspec,
        bridge_evidence_signing_key=key,
        expect_returncode=1,
    )

    assert payload is None
    # Argparse fires the --bridge-evidence-out / --ao-operator-runspec
    # pairing check first, so the stderr message points at that pair.
    assert "--bridge-evidence-out" in result.stderr


def test_missing_bridge_evidence_signing_key_surfaces_in_missing_inputs(
    tmp_path: Path,
) -> None:
    """A non-existent --bridge-evidence-signing-key path is reported as
    missing_inputs (no exception, no partial state, no bridge file).
    """
    fixture = _seed_fixture(tmp_path)
    runspec = _write_real_runspec(tmp_path)
    fake_ao2 = tmp_path / "ao2"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    bridge_out = tmp_path / "bridge-evidence.json"
    _write_fake_ao2(path=fake_ao2, payloads={}, evidence_pack_out=out)

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=tmp_path / "target",
        workdir=tmp_path / "workdir",
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        ao_operator_runspec=runspec,
        bridge_evidence_out=bridge_out,
        bridge_evidence_signing_key=tmp_path / "no-such-key.pem",
    )

    assert payload is not None
    assert payload["status"] == "missing_inputs"
    assert any(
        m.startswith("bridge_evidence_signing_key_not_found:")
        for m in payload["missing"]
    )
    assert not bridge_out.exists()


def test_bridge_evidence_signing_key_echoed_in_input_summary(
    tmp_path: Path,
) -> None:
    """When --bridge-evidence-signing-key is supplied (even if the file is
    missing) the input summary echoes the resolved path + signer id so a
    failed-run audit shows what the orchestrator was asked to do.
    """
    fixture = _seed_fixture(tmp_path)
    runspec = _write_real_runspec(tmp_path)
    fake_ao2 = tmp_path / "ao2"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    bridge_out = tmp_path / "bridge-evidence.json"
    key_path = tmp_path / "no-such-key.pem"
    _write_fake_ao2(path=fake_ao2, payloads={}, evidence_pack_out=out)

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=tmp_path / "target",
        workdir=tmp_path / "workdir",
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        ao_operator_runspec=runspec,
        bridge_evidence_out=bridge_out,
        bridge_evidence_signing_key=key_path,
        bridge_evidence_signer_id="ao2-test-bridge-signer",
    )

    assert payload is not None
    assert payload["status"] == "missing_inputs"
    inputs = payload["inputs"]
    assert inputs["bridge_evidence_signing_key"] == str(key_path)
    assert inputs["bridge_evidence_signer_id"] == "ao2-test-bridge-signer"


def test_bridge_evidence_signer_id_omitted_from_summary_when_no_key(
    tmp_path: Path,
) -> None:
    """The default signer id (``ao2-factory-bridge``) must NOT appear in the
    input summary when no --bridge-evidence-signing-key was supplied; the
    summary should treat the signing pair as a single feature.
    """
    fixture = _seed_fixture(tmp_path)
    runspec = _write_real_runspec(tmp_path)
    fake_ao2 = tmp_path / "ao2"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    bridge_out = tmp_path / "bridge-evidence.json"
    _write_fake_ao2(path=fake_ao2, payloads={}, evidence_pack_out=out)

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=tmp_path / "target",
        workdir=tmp_path / "workdir",
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        ao_operator_runspec=runspec,
        bridge_evidence_out=bridge_out,
    )

    assert payload is not None
    inputs = payload["inputs"]
    assert inputs["bridge_evidence_signing_key"] is None
    assert inputs["bridge_evidence_signer_id"] is None


# ---------------------------------------------------------------------------
# AO2_BIN-gated end-to-end: real ao2 binary signs the bridge evidence, the
# orchestrator writes the AO2-native schema + signed sidecars, and
# ``ao2 factory verify-bridge-evidence`` accepts the result.
# ---------------------------------------------------------------------------


def _ao2_binary_available() -> bool:
    release = ROOT.parent / "ao2" / "target" / "release" / "ao2"
    if release.is_file():
        return True
    debug = ROOT.parent / "ao2" / "target" / "debug" / "ao2"
    return debug.is_file()


def _resolve_ao2_binary() -> str:
    release = ROOT.parent / "ao2" / "target" / "release" / "ao2"
    debug = ROOT.parent / "ao2" / "target" / "debug" / "ao2"
    return str(release if release.is_file() else debug)


def _load_orchestrator_module():
    """Load the orchestrator module so the helper functions can be called
    directly (the rest of the suite uses the script via subprocess)."""

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "ao2_factory_compat_nightly_run", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


import pytest  # noqa: E402 — kept local to the AO2_BIN-gated section


@pytest.mark.skipif(
    not _ao2_binary_available(),
    reason="ao2 binary not built; rerun with cargo build -p ao2-cli",
)
def test_build_bridge_evidence_via_cli_emits_ao2_native_schema_and_sidecars(
    tmp_path: Path,
) -> None:
    """Direct call to the new helper exercises the full signing chain.

    Verifies:
    * The bridge evidence file is written to the requested path.
    * The schema is ``ao2.factory-bridge.v1`` (AO2-native), NOT the
      legacy ao-operator compat schema the Python helper emits.
    * The three signed sidecars produced by ao2 are present on disk
      (``.signed-payload.json``, ``.json.sig``, ``.public.pem``).
    * ``ao2 factory verify-bridge-evidence`` accepts the signed evidence.
    * The returned dict surfaces the AO2-native fields the rest of the
      orchestrator consumes (``mapping``, ``resolved_roles``,
      ``governed_run_plan``).
    """
    ao2_bin = _resolve_ao2_binary()

    # Generate a fresh signing key via `ao2 workbench support-keygen` so we
    # avoid taking a runtime dependency on `cryptography` or `openssl` here.
    key_path = tmp_path / "bridge-signing-key.pem"
    keygen = subprocess.run(
        [
            ao2_bin,
            "workbench",
            "support-keygen",
            "--out",
            str(key_path),
            "--bits",
            "2048",
            "--json",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert keygen.returncode == 0, keygen.stderr
    assert key_path.is_file()

    runspec_path = _write_real_runspec(tmp_path)
    bridge_out = tmp_path / "ao2-native-bridge-evidence.json"

    module = _load_orchestrator_module()
    evidence = module._build_bridge_evidence_via_cli(
        ao2_binary=ao2_bin,
        ao_operator_runspec=runspec_path,
        bridge_evidence_out=bridge_out,
        signing_key=key_path,
        signer_id="ao2-test-bridge-signer",
    )

    # File materialised at the requested path with the AO2-native schema.
    assert bridge_out.is_file()
    on_disk = json.loads(bridge_out.read_text(encoding="utf-8"))
    assert on_disk["schema"] == "ao2.factory-bridge.v1"
    assert on_disk == evidence

    # AO2-native fields the orchestrator's downstream code consumes.
    assert isinstance(evidence.get("mapping"), dict)
    assert isinstance(evidence.get("resolved_roles"), list)
    assert isinstance(evidence.get("governed_run_plan"), dict)

    # Sidecars from the signing step are present.
    signed_payload = Path(str(bridge_out) + ".signed-payload.json")
    if not signed_payload.is_file():
        signed_payload = bridge_out.with_suffix(".signed-payload.json")
    assert signed_payload.is_file()
    detached_sig = Path(str(bridge_out) + ".sig")
    if not detached_sig.is_file():
        detached_sig = bridge_out.with_suffix(".sig")
    assert detached_sig.is_file()
    public_pem = Path(str(bridge_out) + ".public.pem")
    if not public_pem.is_file():
        public_pem = bridge_out.with_suffix(".public.pem")
    assert public_pem.is_file()

    # AO2's own verifier accepts the signed evidence end-to-end.
    verify = subprocess.run(
        [
            ao2_bin,
            "factory",
            "verify-bridge-evidence",
            "--evidence",
            str(bridge_out),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert verify.returncode == 0, (verify.stdout, verify.stderr)


@pytest.mark.skipif(
    not _ao2_binary_available(),
    reason="ao2 binary not built; rerun with cargo build -p ao2-cli",
)
def test_build_bridge_evidence_via_cli_raises_when_runspec_invalid(
    tmp_path: Path,
) -> None:
    """When the underlying ``ao2 factory bridge`` invocation fails (e.g. the
    runspec doesn't exist), ``_build_bridge_evidence_via_cli`` raises
    ``_AO2Failure`` with stage=``bridge-canonicalize`` so the orchestrator
    surfaces a normal ``failed`` summary instead of leaking a Python
    traceback.
    """
    ao2_bin = _resolve_ao2_binary()
    module = _load_orchestrator_module()

    bridge_out = tmp_path / "ao2-native-bridge-evidence.json"
    bogus_runspec = tmp_path / "no-such-runspec.yaml"
    bogus_key = tmp_path / "no-such-key.pem"
    bogus_key.write_text("-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n", encoding="utf-8")

    with pytest.raises(module._AO2Failure) as excinfo:
        module._build_bridge_evidence_via_cli(
            ao2_binary=ao2_bin,
            ao_operator_runspec=bogus_runspec,
            bridge_evidence_out=bridge_out,
            signing_key=bogus_key,
            signer_id="ao2-test-bridge-signer",
        )
    assert excinfo.value.stage == "bridge-canonicalize"
    assert not bridge_out.exists()


# ---------------------------------------------------------------------------
# Phase 2 exit-gate #4: surface + assert governed_run_plan.native_gates
# declaration (slice 15). ao2 commit e129070 added the AO2-native fields
# `decision_owner`, `factory_v3_decision_owner`, and `native_gates` to the
# `governed_run_plan` block of `ao2.factory-bridge.v1` evidence. Factory-v3
# is the consumer; this section asserts that:
# - The bridge summary echoes the new fields (so audits + status artifacts
#   surface AO2's run-plan declaration).
# - The boundary check rejects any AO2-native bridge evidence claiming
#   factory_v3 owns a decision (factory_v3_decision_owner must be
#   "parity_oracle_only" when present).
# - Legacy Python-helper-produced bridge evidence with no
#   `governed_run_plan` block keeps working (the new fields are None;
#   the boundary check is a no-op).
# ---------------------------------------------------------------------------


def test_bridge_evidence_summary_surfaces_governed_run_plan_fields() -> None:
    module = _load_orchestrator_module()
    evidence = {
        "schema": "ao2.factory-bridge.v1",
        "status": "mapping_resolved_dry_run",
        "mapping": {"digest": "deadbeef", "version": "v1"},
        "resolved_roles": [
            {"role_id": "planner-intake", "ao2_provider_contract_id": "pc-1"},
        ],
        "unknown_roles": [],
        "input_runspec": {"sha256": "abc123"},
        "governed_run_plan": {
            "schema": "ao2.governed-run-plan.v1",
            "status": "materialized_dry_run",
            "decision_owner": "ao2_native_evaluator_closer",
            "factory_v3_decision_owner": "parity_oracle_only",
            "native_gates": [
                {
                    "stage": "midpoint",
                    "emits": "ao2.obligation-gate.midpoint.v1",
                },
                {
                    "stage": "closure",
                    "emits": "ao2.evaluator-closer-decision.v1",
                },
            ],
        },
    }
    summary = module._bridge_evidence_summary(evidence)
    assert summary["governed_run_plan_schema"] == "ao2.governed-run-plan.v1"
    assert summary["governed_run_plan_status"] == "materialized_dry_run"
    assert (
        summary["governed_run_plan_decision_owner"]
        == "ao2_native_evaluator_closer"
    )
    assert (
        summary["governed_run_plan_factory_v3_decision_owner"]
        == "parity_oracle_only"
    )
    assert summary["governed_run_plan_native_gates_count"] == 2
    assert summary["governed_run_plan_native_gate_stages"] == [
        "midpoint",
        "closure",
    ]
    assert summary["governed_run_plan_native_gate_emits"] == [
        "ao2.obligation-gate.midpoint.v1",
        "ao2.evaluator-closer-decision.v1",
    ]


def test_bridge_evidence_summary_governed_run_plan_fields_none_when_absent() -> None:
    """Legacy Python-helper bridge evidence has no `governed_run_plan` block;
    the summary surfaces None / 0 / [] for the new fields rather than
    raising. Preserves back-compat for the default unsigned code path."""
    module = _load_orchestrator_module()
    evidence = {
        "schema": "ao-operator/start-ao2-run-from-role-runspec/v1",
        "status": "mapping_resolved_dry_run",
        "mapping": {"digest": "deadbeef", "version": "v1"},
        "resolved_roles": [],
        "unknown_roles": [],
        "input_runspec": {"sha256": "abc123"},
    }
    summary = module._bridge_evidence_summary(evidence)
    assert summary["governed_run_plan_schema"] is None
    assert summary["governed_run_plan_status"] is None
    assert summary["governed_run_plan_decision_owner"] is None
    assert summary["governed_run_plan_factory_v3_decision_owner"] is None
    assert summary["governed_run_plan_native_gates_count"] == 0
    assert summary["governed_run_plan_native_gate_stages"] == []
    assert summary["governed_run_plan_native_gate_emits"] == []


def test_factory_v3_decision_owner_boundary_accepts_parity_oracle_only() -> None:
    module = _load_orchestrator_module()
    evidence = {
        "schema": "ao2.factory-bridge.v1",
        "governed_run_plan": {
            "factory_v3_decision_owner": "parity_oracle_only",
        },
    }
    # No exception raised.
    module._assert_factory_v3_decision_owner_boundary(evidence)


def test_factory_v3_decision_owner_boundary_rejects_other_owners() -> None:
    """Any value other than `parity_oracle_only` is a boundary violation —
    ao-operator is the parity oracle, never the decision owner."""
    module = _load_orchestrator_module()
    evidence = {
        "schema": "ao2.factory-bridge.v1",
        "governed_run_plan": {
            "factory_v3_decision_owner": "factory_v3_evaluator_closer",
        },
    }
    import pytest as _pt
    with _pt.raises(module._AO2Failure) as excinfo:
        module._assert_factory_v3_decision_owner_boundary(evidence)
    assert excinfo.value.stage == "bridge-canonicalize"
    assert "factory_v3_decision_owner" in excinfo.value.reason
    assert "parity_oracle_only" in excinfo.value.reason


def test_factory_v3_decision_owner_boundary_silent_when_governed_run_plan_absent() -> None:
    """Legacy Python-helper bridge evidence has no `governed_run_plan` block;
    the boundary check is a no-op. Preserves back-compat."""
    module = _load_orchestrator_module()
    evidence = {
        "schema": "ao-operator/start-ao2-run-from-role-runspec/v1",
        "resolved_roles": [],
    }
    # No exception raised.
    module._assert_factory_v3_decision_owner_boundary(evidence)


def test_factory_v3_decision_owner_boundary_silent_when_field_absent() -> None:
    """AO2-native bridge evidence without the explicit
    factory_v3_decision_owner field (e.g. from an older ao2 binary that
    predates commit e129070) keeps working — the boundary check only
    fires when the field is present and wrong."""
    module = _load_orchestrator_module()
    evidence = {
        "schema": "ao2.factory-bridge.v1",
        "governed_run_plan": {
            "schema": "ao2.governed-run-plan.v1",
            "status": "materialized_dry_run",
        },
    }
    module._assert_factory_v3_decision_owner_boundary(evidence)


@pytest.mark.skipif(
    not _ao2_binary_available(),
    reason="ao2 binary not built; rerun with cargo build -p ao2-cli",
)
def test_real_ao2_bridge_emits_expected_governed_run_plan_declaration(
    tmp_path: Path,
) -> None:
    """End-to-end: a real `ao2 factory bridge` invocation produces evidence
    whose `governed_run_plan` block matches the slice-15 contract — the
    decision_owner is `ao2_native_evaluator_closer`,
    factory_v3_decision_owner is `parity_oracle_only`, and the native_gates
    array contains the midpoint + closure stages emitting the expected
    AO2-native schemas. This guards against future ao2 changes that would
    drop or rename these fields silently.
    """
    ao2_bin = _resolve_ao2_binary()
    runspec_path = _write_real_runspec(tmp_path)
    bridge_out = tmp_path / "ao2-native-bridge-evidence.json"
    completed = subprocess.run(
        [
            ao2_bin,
            "factory",
            "bridge",
            "--runspec",
            str(runspec_path),
            "--out",
            str(bridge_out),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    evidence = json.loads(bridge_out.read_text(encoding="utf-8"))
    plan = evidence.get("governed_run_plan") or {}
    assert plan.get("schema") == "ao2.governed-run-plan.v1"
    assert plan.get("decision_owner") == "ao2_native_evaluator_closer"
    assert plan.get("factory_v3_decision_owner") == "parity_oracle_only"
    gates = plan.get("native_gates") or []
    stages = [gate.get("stage") for gate in gates]
    emits = [gate.get("emits") for gate in gates]
    assert "midpoint" in stages
    assert "closure" in stages
    assert "ao2.obligation-gate.midpoint.v1" in emits
    assert "ao2.evaluator-closer-decision.v1" in emits

    # Factory-v3's boundary check must accept the AO2-emitted plan.
    module = _load_orchestrator_module()
    module._assert_factory_v3_decision_owner_boundary(evidence)
    # And the summary must surface the same values the boundary check saw.
    summary = module._bridge_evidence_summary(evidence)
    assert (
        summary["governed_run_plan_decision_owner"]
        == "ao2_native_evaluator_closer"
    )
    assert (
        summary["governed_run_plan_factory_v3_decision_owner"]
        == "parity_oracle_only"
    )
    assert summary["governed_run_plan_native_gates_count"] == len(gates)


# ---------------------------------------------------------------------------
# Phase 2 exit-gate #3: surface governed_run_plan_* in Hermes context (slice 16)
#
# Slice 15 surfaced the AO2-native `governed_run_plan` fields in the
# orchestrator's *bridge-evidence* summary. Downstream observability
# (the Hermes AO2-refs context export) still dropped them. Slice 16:
#   1. Extends `_refs_from_bridge_evidence` in
#      `scripts/hermes_context_with_ao2_refs.py` to accept both bridge-
#      evidence schemas (the legacy Python-helper schema AND the AO2-
#      native `ao2.factory-bridge.v1` schema). For the AO2-native
#      schema, it extracts the `governed_run_plan_*` fields. (Tested
#      directly in `test_hermes_context_with_ao2_refs.py`.)
#   2. Extends `_hermes_context_summary` in this orchestrator to mirror
#      those new ref keys at the status-summary surface so a normal
#      nightly status artifact carries the AO2 run-plan declaration.
# ---------------------------------------------------------------------------


def test_hermes_context_summary_surfaces_governed_run_plan_fields() -> None:
    """Slice 16: when the Hermes payload's `ao2_refs` block carries
    governed_run_plan_* keys (set when the bridge evidence is
    AO2-native), the summary must surface every one of them at the
    status-artifact tier."""
    module = _load_orchestrator_module()
    payload = {
        "schema": "ao-operator/hermes-context-with-ao2-refs/v1",
        "slug": "ao2-native-run",
        "factory_v3_local_paths_omitted": True,
        "ao2_refs": {
            "ao2_provider_contract_mapping_digest": "c" * 64,
            "ao2_invocation_status": "ao2_native_bridge_succeeded",
            "ao2_governed_run_plan_schema": "ao2.governed-run-plan.v1",
            "ao2_governed_run_plan_status": "materialized_dry_run",
            "ao2_governed_run_plan_decision_owner": (
                "ao2_native_evaluator_closer"
            ),
            "ao2_governed_run_plan_factory_v3_decision_owner": (
                "parity_oracle_only"
            ),
            "ao2_governed_run_plan_native_gates_count": 2,
            "ao2_governed_run_plan_native_gate_stages": [
                "midpoint",
                "closure",
            ],
            "ao2_governed_run_plan_native_gate_emits": [
                "ao2.obligation-gate.midpoint.v1",
                "ao2.evaluator-closer-decision.v1",
            ],
        },
    }
    summary = module._hermes_context_summary(payload)
    assert (
        summary["ao2_governed_run_plan_schema"]
        == "ao2.governed-run-plan.v1"
    )
    assert (
        summary["ao2_governed_run_plan_status"] == "materialized_dry_run"
    )
    assert (
        summary["ao2_governed_run_plan_decision_owner"]
        == "ao2_native_evaluator_closer"
    )
    assert (
        summary["ao2_governed_run_plan_factory_v3_decision_owner"]
        == "parity_oracle_only"
    )
    assert summary["ao2_governed_run_plan_native_gates_count"] == 2
    assert summary["ao2_governed_run_plan_native_gate_stages"] == [
        "midpoint",
        "closure",
    ]
    assert summary["ao2_governed_run_plan_native_gate_emits"] == [
        "ao2.obligation-gate.midpoint.v1",
        "ao2.evaluator-closer-decision.v1",
    ]
    # The new keys must appear in the sorted ao2_ref_keys list too.
    assert (
        "ao2_governed_run_plan_factory_v3_decision_owner"
        in summary["ao2_ref_keys"]
    )


def test_hermes_context_summary_governed_run_plan_fields_default_when_absent() -> None:
    """Legacy Python-helper bridge evidence has no `governed_run_plan`
    block, so the helper's refs dict has no governed_run_plan_* keys
    either. The summary must default count to 0, lists to [], and the
    optional scalar fields to None so the status artifact shape stays
    stable across both bridge-evidence schemas."""
    module = _load_orchestrator_module()
    payload = {
        "schema": "ao-operator/hermes-context-with-ao2-refs/v1",
        "slug": "legacy-python-helper-run",
        "factory_v3_local_paths_omitted": True,
        "ao2_refs": {
            "ao2_provider_contract_mapping_digest": "c" * 64,
            "ao2_plan_sha256": "d" * 64,
            "ao2_invocation_status": "ao2_plan_succeeded",
        },
    }
    summary = module._hermes_context_summary(payload)
    assert summary["ao2_governed_run_plan_schema"] is None
    assert summary["ao2_governed_run_plan_status"] is None
    assert summary["ao2_governed_run_plan_decision_owner"] is None
    assert summary["ao2_governed_run_plan_factory_v3_decision_owner"] is None
    assert summary["ao2_governed_run_plan_native_gates_count"] == 0
    assert summary["ao2_governed_run_plan_native_gate_stages"] == []
    assert summary["ao2_governed_run_plan_native_gate_emits"] == []
    # The legacy ref keys must still flow through (slice 16 must not
    # have broken back-compat).
    assert summary["ao2_provider_contract_mapping_digest"] == "c" * 64
    assert summary["ao2_plan_sha256"] == "d" * 64


def test_hermes_context_summary_governed_run_plan_lists_are_independent() -> None:
    """The summary helper must read out fresh values from `refs.get`
    rather than re-using a shared mutable default; defensively guard
    against future refactors that swap the literal `[]` for a module-
    level constant."""
    module = _load_orchestrator_module()
    payload_a = {
        "schema": "ao-operator/hermes-context-with-ao2-refs/v1",
        "ao2_refs": {},
    }
    payload_b = {
        "schema": "ao-operator/hermes-context-with-ao2-refs/v1",
        "ao2_refs": {},
    }
    summary_a = module._hermes_context_summary(payload_a)
    summary_b = module._hermes_context_summary(payload_b)
    summary_a["ao2_governed_run_plan_native_gate_stages"].append("midpoint")
    assert summary_b["ao2_governed_run_plan_native_gate_stages"] == []


@pytest.mark.skipif(
    not _ao2_binary_available(),
    reason="ao2 binary not built; rerun with cargo build -p ao2-cli",
)
def test_ao2_native_bridge_evidence_flows_into_hermes_context_summary(
    tmp_path: Path,
) -> None:
    """End-to-end: a real `ao2 factory bridge` invocation produces
    AO2-native bridge evidence; feeding it through the orchestrator's
    Hermes-context builder + summary trim yields a summary whose
    governed_run_plan_* fields match the AO2-emitted declaration.

    This is the slice-16 acceptance test: the slice-12 fail-closed
    passthrough verifier already ensures the bridge evidence is
    well-formed, and the slice-15 boundary check rejects boundary
    violations -- this test proves the *observability* layer
    surfaces the AO2 declaration in the status artifact tier.
    """
    ao2_bin = _resolve_ao2_binary()
    runspec_path = _write_real_runspec(tmp_path)
    bridge_out = tmp_path / "ao2-native-bridge-evidence.json"
    completed = subprocess.run(
        [
            ao2_bin,
            "factory",
            "bridge",
            "--runspec",
            str(runspec_path),
            "--out",
            str(bridge_out),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    bridge_evidence = json.loads(bridge_out.read_text(encoding="utf-8"))

    pack_path = tmp_path / "ao2-evidence-pack.json"
    pack_path.write_text(
        json.dumps(
            {
                "schema_version": "ao2.evidence-pack.v1",
                "run_id": "r-slice-16-acceptance-1",
                "closure_status": "accepted",
                "artifacts": [],
            }
        ),
        encoding="utf-8",
    )
    hermes_out = tmp_path / "hermes-context.json"

    module = _load_orchestrator_module()
    payload = module._build_hermes_context_payload(
        slug="slice-16-acceptance",
        bridge_evidence=bridge_evidence,
        evidence_pack_path=pack_path,
        hermes_context_out=hermes_out,
    )
    refs = payload["ao2_refs"]
    assert (
        refs["ao2_governed_run_plan_factory_v3_decision_owner"]
        == "parity_oracle_only"
    )
    assert refs["ao2_governed_run_plan_native_gates_count"] >= 2

    summary = module._hermes_context_summary(payload)
    assert (
        summary["ao2_governed_run_plan_factory_v3_decision_owner"]
        == "parity_oracle_only"
    )
    assert "midpoint" in summary["ao2_governed_run_plan_native_gate_stages"]
    assert "closure" in summary["ao2_governed_run_plan_native_gate_stages"]
    # The summary must also still surface the AO2 run id sourced from
    # the evidence pack -- the slice-16 changes must not have shadowed
    # any pre-existing summary field.
    assert summary["ao2_run_id"] == "r-slice-16-acceptance-1"
    # And the on-disk Hermes context file must match the in-memory
    # payload byte-for-byte through pretty-print + sort.
    on_disk = json.loads(hermes_out.read_text(encoding="utf-8"))
    assert on_disk == payload


# ---------------------------------------------------------------------------
# Phase 2 exit-gate #3, strict-mode CP-receipt presence check.
#
# Slice B wires `--require-all-ao2-ref-categories` through the factory-compat
# orchestrator so the Hermes context payload refuses to land unless ALL four
# AO2 ref categories (bridge_evidence, evidence_pack, memory_record,
# cp_receipt) are present. Tests below cover the three documented paths:
#
#   1. Strict-mode passes when all four categories supplied (cp_receipt
#      pin enables the full chain).
#   2. Strict-mode rejects with stage=hermes-context-strict-mode when
#      cp_receipt is absent (the typical pre-CP-producer environment).
#   3. Default (non-strict) mode continues to accept payloads with missing
#      categories so the opt-in semantics stay intact.
# ---------------------------------------------------------------------------


def test_strict_mode_passes_when_all_four_ao2_ref_categories_present(
    tmp_path: Path,
) -> None:
    """Strict mode emits the payload when bridge + pack + memory + cp_receipt all land."""
    fixture = _seed_fixture(tmp_path)
    target = tmp_path / "target"
    workdir = tmp_path / "workdir"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    hermes_out = tmp_path / "hermes-context.json"
    bridge_out = tmp_path / "bridge-evidence.json"
    record_out = tmp_path / "memory-record.json"
    fake_ao2 = tmp_path / "ao2"
    runspec = _write_real_runspec(tmp_path)
    run_id = "strict-pass"

    receipt_path = tmp_path / "cp-ingest-receipt.json"
    receipt_value = {
        "schema_version": "ao2.cp-ingest-receipt.v1",
        "sha256": "abc1234567890abcdef1234567890abcdef1234567890abcdef1234567890abc",
        "stored_at": "2026-05-25T03:30:00Z",
        "ingested_schema_version": "ao2.evidence-pack.v1",
    }
    receipt_path.write_text(json.dumps(receipt_value), encoding="utf-8")

    payloads = _fake_ao2_payloads(
        factory_target=target,
        run_id=run_id,
        evidence_pack_out=out,
    )
    pack_body = {
        "schema_version": AO2_EVIDENCE_PACK_SCHEMA,
        "run_id": run_id,
        "closure_status": "closed",
    }
    _write_fake_ao2(
        path=fake_ao2,
        payloads=payloads,
        evidence_pack_out=out,
        pack_body=pack_body,
        memory_payload=_fake_memory_payload(record_id=f"mem-{run_id}-1"),
    )

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=target,
        workdir=workdir,
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        run_id=run_id,
        ao_operator_runspec=runspec,
        bridge_evidence_out=bridge_out,
        hermes_context_out=hermes_out,
        hermes_context_slug=run_id,
        control_plane_receipt=receipt_path,
        memory_record_out=record_out,
        require_all_ao2_ref_categories=True,
    )

    assert payload is not None
    assert payload["status"] == "produced"
    # The strict-mode flag is echoed in the input summary so operators can
    # tell from the on-disk artifact whether the strict invariant was
    # enforced for this run.
    assert payload["inputs"]["require_all_ao2_ref_categories"] is True
    # All four AO2 ref categories pinned in the Hermes payload.
    refs = json.loads(hermes_out.read_text(encoding="utf-8"))["ao2_refs"]
    assert refs["ao2_run_id"] == run_id
    assert refs["ao2_evidence_pack_sha256"]
    assert refs["ao2_memory_record_id"] == f"mem-{run_id}-1"
    assert refs["control_plane_ingest_sha256"] == receipt_value["sha256"]


def test_strict_mode_rejects_when_cp_receipt_absent(tmp_path: Path) -> None:
    """Strict mode surfaces stage=hermes-context-strict-mode with the missing categories."""
    fixture = _seed_fixture(tmp_path)
    target = tmp_path / "target"
    workdir = tmp_path / "workdir"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    hermes_out = tmp_path / "hermes-context.json"
    bridge_out = tmp_path / "bridge-evidence.json"
    record_out = tmp_path / "memory-record.json"
    fake_ao2 = tmp_path / "ao2"
    runspec = _write_real_runspec(tmp_path)
    run_id = "strict-missing-cp"

    payloads = _fake_ao2_payloads(
        factory_target=target,
        run_id=run_id,
        evidence_pack_out=out,
    )
    pack_body = {
        "schema_version": AO2_EVIDENCE_PACK_SCHEMA,
        "run_id": run_id,
        "closure_status": "closed",
    }
    _write_fake_ao2(
        path=fake_ao2,
        payloads=payloads,
        evidence_pack_out=out,
        pack_body=pack_body,
        memory_payload=_fake_memory_payload(record_id=f"mem-{run_id}-1"),
    )

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=target,
        workdir=workdir,
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        run_id=run_id,
        ao_operator_runspec=runspec,
        bridge_evidence_out=bridge_out,
        hermes_context_out=hermes_out,
        hermes_context_slug=run_id,
        # Deliberately omit control_plane_receipt to trigger strict mode.
        memory_record_out=record_out,
        require_all_ao2_ref_categories=True,
    )

    assert payload is not None
    assert payload["status"] == "failed"
    assert payload["stage"] == "hermes-context-strict-mode"
    # The failure reason must name the specific missing category so the
    # operator can immediately tell which producer is unwired.
    assert "cp_receipt" in payload["failure_reason"]
    # And the input summary still echoes that strict mode was requested.
    assert payload["inputs"]["require_all_ao2_ref_categories"] is True
    # No Hermes context payload was written when strict mode rejected.
    assert not hermes_out.exists()


def test_default_mode_accepts_payload_with_missing_categories(
    tmp_path: Path,
) -> None:
    """Default (non-strict) mode keeps accepting payloads missing some categories."""
    fixture = _seed_fixture(tmp_path)
    target = tmp_path / "target"
    workdir = tmp_path / "workdir"
    out = tmp_path / "pack.json"
    summary = tmp_path / "summary.json"
    hermes_out = tmp_path / "hermes-context.json"
    bridge_out = tmp_path / "bridge-evidence.json"
    fake_ao2 = tmp_path / "ao2"
    runspec = _write_real_runspec(tmp_path)
    run_id = "default-mode"

    payloads = _fake_ao2_payloads(
        factory_target=target,
        run_id=run_id,
        evidence_pack_out=out,
    )
    pack_body = {
        "schema_version": AO2_EVIDENCE_PACK_SCHEMA,
        "run_id": run_id,
        "closure_status": "closed",
    }
    _write_fake_ao2(
        path=fake_ao2,
        payloads=payloads,
        evidence_pack_out=out,
        pack_body=pack_body,
    )

    payload, _ = run_orchestrator(
        ao2_fixture=fixture,
        target=target,
        workdir=workdir,
        evidence_pack_out=out,
        write_json=summary,
        ao2_binary=str(fake_ao2),
        run_id=run_id,
        ao_operator_runspec=runspec,
        bridge_evidence_out=bridge_out,
        hermes_context_out=hermes_out,
        hermes_context_slug=run_id,
        # No memory_record_out, no control_plane_receipt -- categories
        # missing -- but strict mode is off so the producer still emits.
    )

    assert payload is not None
    assert payload["status"] == "produced"
    # Default value of the strict flag is echoed as False in the summary.
    assert payload["inputs"]["require_all_ao2_ref_categories"] is False
    # The Hermes context still landed with at least one AO2 ref (the
    # bridge mapping digest + evidence-pack sha + run id) -- the
    # contract that strict mode tightens but default mode permits.
    refs = json.loads(hermes_out.read_text(encoding="utf-8"))["ao2_refs"]
    assert refs["ao2_run_id"] == run_id
    assert refs["ao2_evidence_pack_sha256"]
    assert "control_plane_ingest_sha256" not in refs
    assert "ao2_memory_record_id" not in refs
