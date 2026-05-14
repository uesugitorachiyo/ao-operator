#!/usr/bin/env python3
"""Verify AO Operator evidence pack signatures and tamper-evidence."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import evidence_pack_writer

MAX_TAR_MEMBERS = 10_000
MAX_TAR_BYTES = 1_000_000_000
REPLAY_NETWORK_DENYLIST = {
    "curl",
    "wget",
    "nc",
    "netcat",
    "ssh",
    "scp",
    "sftp",
    "ftp",
    "telnet",
}


def _load_manifest(pack_root: Path) -> tuple[dict[str, object], bytes]:
    body = (pack_root / "manifest.json").read_bytes()
    return json.loads(body.decode("utf-8")), body


def _safe_extract_tar(tar_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    dest_root = dest.resolve()
    with tarfile.open(tar_path) as tf:
        root: Path | None = None
        total_size = 0
        for index, member in enumerate(tf.getmembers(), start=1):
            if index > MAX_TAR_MEMBERS:
                raise ValueError("tar member count exceeds limit")
            member_path = Path(member.name)
            if not member.name or member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"unsafe tar member path: {member.name}")
            parts = member_path.parts
            if not parts:
                raise ValueError(f"unsafe tar member path: {member.name}")
            member_root = dest / parts[0]
            if root is None:
                root = member_root
            elif member_root != root:
                raise ValueError(f"multiple tar roots are not allowed: {member.name}")
            target = (dest / member_path).resolve()
            if os.path.commonpath([str(target), str(dest_root)]) != str(dest_root):
                raise ValueError(f"unsafe tar member path: {member.name}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ValueError(f"unsafe tar member type: {member.name}")
            total_size += member.size
            if total_size > MAX_TAR_BYTES:
                raise ValueError("tar payload size exceeds limit")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tf.extractfile(member)
            if source is None:
                raise ValueError(f"unable to read tar member: {member.name}")
            with source, target.open("xb") as out:
                shutil.copyfileobj(source, out)
    if root is None:
        raise ValueError("archive is empty")
    return root


def _materialize_pack(path: Path, scratch: Path) -> Path:
    if path.is_dir():
        return path
    if path.name.endswith(".tar.zst"):
        zstd = shutil.which("zstd")
        if zstd is None:
            raise ImportError("install zstandard or zstd CLI to verify .tar.zst evidence packs")
        tar_path = scratch / path.name.removesuffix(".zst")
        result = subprocess.run(
            [zstd, "-q", "-d", "-o", str(tar_path), str(path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "zstd decompression failed")
        return _safe_extract_tar(tar_path, scratch / "extract")
    if path.name.endswith(".tar"):
        return _safe_extract_tar(path, scratch / "extract")
    raise ValueError(f"unsupported evidence pack path: {path}")


def _sig_input(manifest_bytes: bytes, manifest: dict[str, object]) -> bytes:
    root = str(manifest.get("merkle_root", "")).removeprefix("sha256:")
    return hashlib.sha256(manifest_bytes).digest() + bytes.fromhex(root)


def _verify_signature(pack_root: Path, manifest: dict[str, object], manifest_bytes: bytes, hmac_key: bytes | None) -> tuple[str, str]:
    algo = manifest.get("signature_algo")
    signature = (pack_root / "signatures" / "pack.sig").read_bytes()
    if algo == "HMAC-SHA256":
        if hmac_key is None:
            return ("FAIL", "hmac_key_required")
        expected = hmac.new(hmac_key, _sig_input(manifest_bytes, manifest), hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return ("FAIL", "signature_mismatch")
        pubkey = (pack_root / "signatures" / "pubkey").read_bytes()
        if pubkey != hashlib.sha256(hmac_key).digest():
            return ("FAIL", "public_material_mismatch")
        return ("PASS", "")
    if algo == "Ed25519":
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        except ImportError:
            return ("FAIL", "ed25519_verification_requires_optional_cryptography")
        key = serialization.load_pem_public_key((pack_root / "signatures" / "pubkey").read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            return ("FAIL", "ed25519_public_key_required")
        try:
            key.verify(signature, _sig_input(manifest_bytes, manifest))
        except Exception:
            return ("FAIL", "signature_mismatch")
        return ("PASS", "")
    return ("FAIL", f"unsupported_signature_algo:{algo}")


def _verify_artifacts(pack_root: Path) -> list[str]:
    errors: list[str] = []
    artifact_root = pack_root / "artifacts"
    if not artifact_root.exists():
        return errors
    for sha_dir in sorted(path for path in artifact_root.iterdir() if path.is_dir()):
        expected = sha_dir.name
        for artifact in sorted(path for path in sha_dir.iterdir() if path.is_file()):
            observed = evidence_pack_writer._sha256_file(artifact)
            if observed != expected:
                errors.append(f"artifact_sha_mismatch:{artifact.relative_to(pack_root)}")
    return errors


def _read_events(pack_root: Path) -> list[dict[str, object]]:
    events_path = pack_root / "events.ndjson"
    if not events_path.exists():
        return []
    events: list[dict[str, object]] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            events.append({"_parse_error": line})
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def _task_ids(manifest: dict[str, object]) -> list[str]:
    tasks = manifest.get("tasks", [])
    if not isinstance(tasks, list):
        return []
    ids: list[str] = []
    for task in tasks:
        if isinstance(task, dict):
            task_id = str(task.get("task_id", ""))
            if task_id:
                ids.append(task_id)
    return ids


def _check_event_task_coverage(manifest: dict[str, object], events: list[dict[str, object]]) -> list[str]:
    observed = {str(event.get("task_id")) for event in events if event.get("task_id")}
    return [
        f"event_task_missing:{task_id}"
        for task_id in _task_ids(manifest)
        if task_id not in observed
    ]


def _check_transcript_paths(pack_root: Path, manifest: dict[str, object]) -> list[str]:
    errors: list[str] = []
    for task in manifest.get("tasks", []):
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("task_id", ""))
        transcript_path = str(task.get("transcript_path", ""))
        if transcript_path and not (pack_root / transcript_path).is_file():
            errors.append(f"transcript_missing:{task_id}:{transcript_path}")
    return errors


def _check_artifact_refs(pack_root: Path, manifest: dict[str, object]) -> list[str]:
    errors: list[str] = []
    for task in manifest.get("tasks", []):
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("task_id", ""))
        artifact_shas = task.get("artifact_shas", [])
        if not isinstance(artifact_shas, list):
            errors.append(f"artifact_refs_invalid:{task_id}")
            continue
        for raw in artifact_shas:
            sha = str(raw).removeprefix("sha256:")
            artifact_dir = pack_root / "artifacts" / sha
            if not artifact_dir.is_dir() or not any(path.is_file() for path in artifact_dir.iterdir()):
                errors.append(f"artifact_ref_missing:{task_id}:sha256:{sha}")
    return errors


def _check_deterministic_replay_declarations(
    pack_root: Path, manifest: dict[str, object]
) -> tuple[int, list[str]]:
    errors: list[str] = []
    tasks = manifest.get("tasks", [])
    if not isinstance(tasks, list):
        return (0, ["tasks_invalid"])

    deterministic_tasks = [
        task
        for task in tasks
        if isinstance(task, dict) and task.get("deterministic") is True
    ]
    for task in deterministic_tasks:
        task_id = str(task.get("task_id", ""))
        replay_command = task.get("replay_command")
        if not (
            isinstance(replay_command, list)
            and replay_command
            and all(isinstance(part, str) and part for part in replay_command)
        ):
            errors.append(f"deterministic_replay_command_missing:{task_id}")

        replay_outputs = task.get("replay_outputs")
        if not (
            isinstance(replay_outputs, list)
            and replay_outputs
            and all(isinstance(part, str) and part for part in replay_outputs)
        ):
            errors.append(f"deterministic_replay_outputs_missing:{task_id}")
            continue

        artifact_shas = task.get("artifact_shas", [])
        if not isinstance(artifact_shas, list) or not artifact_shas:
            errors.append(f"deterministic_replay_artifacts_missing:{task_id}")
            continue

        artifact_dirs = [
            pack_root / "artifacts" / str(raw).removeprefix("sha256:")
            for raw in artifact_shas
        ]
        for output in replay_outputs:
            output_name = Path(str(output)).name
            if not any((artifact_dir / output_name).is_file() for artifact_dir in artifact_dirs):
                errors.append(f"deterministic_replay_output_missing:{task_id}:{output}")

    return (len(deterministic_tasks), errors)


def _deterministic_tasks(manifest: dict[str, object]) -> list[dict[str, object]]:
    tasks = manifest.get("tasks", [])
    if not isinstance(tasks, list):
        return []
    return [
        task
        for task in tasks
        if isinstance(task, dict) and task.get("deterministic") is True
    ]


def _replay_command_denial(command: list[str]) -> str:
    if not command:
        return "empty"
    exe = Path(command[0]).name.lower()
    if exe in REPLAY_NETWORK_DENYLIST:
        return exe
    if exe not in {"python", "python3", Path(sys.executable).name.lower()}:
        return exe
    return ""


def _portable_python() -> str:
    override = os.environ.get("FACTORY_V3_PYTHON")
    return override if override else sys.executable


def _resolved_replay_command(command: list[str]) -> list[str]:
    exe = Path(command[0]).name.lower()
    if exe in {"python", "python3", Path(sys.executable).name.lower()}:
        return [_portable_python(), *command[1:]]
    return command


def _replay_env(work_dir: Path) -> dict[str, str]:
    home = work_dir / "home"
    tmp = work_dir / "tmp"
    home.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "TMPDIR": str(tmp),
        "TEMP": str(tmp),
        "TMP": str(tmp),
        "PYTHONNOUSERSITE": "1",
        "NO_PROXY": "*",
        "no_proxy": "*",
        "HTTP_PROXY": "",
        "HTTPS_PROXY": "",
        "ALL_PROXY": "",
        "http_proxy": "",
        "https_proxy": "",
        "all_proxy": "",
        "FACTORY_V3_REPLAY_NETWORK": "disabled",
    }
    if sys.platform == "win32":
        for key in ("SYSTEMROOT", "SystemRoot", "COMSPEC", "PATHEXT"):
            if key in os.environ:
                env[key] = os.environ[key]
    return env


def _task_artifact_sha_set(task: dict[str, object]) -> set[str]:
    artifact_shas = task.get("artifact_shas", [])
    if not isinstance(artifact_shas, list):
        return set()
    return {str(raw).removeprefix("sha256:") for raw in artifact_shas}


def _safe_output_path(work_dir: Path, raw_output: object) -> Path:
    rel = Path(str(raw_output))
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(str(raw_output))
    target = (work_dir / rel).resolve()
    root = work_dir.resolve()
    if os.path.commonpath([str(target), str(root)]) != str(root):
        raise ValueError(str(raw_output))
    return target


def _execute_deterministic_tasks(
    manifest: dict[str, object],
    *,
    timeout_seconds: float,
    scratch: Path,
) -> tuple[list[dict[str, object]], list[str]]:
    reports: list[dict[str, object]] = []
    errors: list[str] = []
    execution_root = scratch / "deterministic-exec"
    execution_root.mkdir()
    for task in _deterministic_tasks(manifest):
        task_id = str(task.get("task_id", ""))
        command = task.get("replay_command", [])
        if not isinstance(command, list):
            command = []
        command = [str(part) for part in command]
        task_report: dict[str, object] = {
            "task_id": task_id,
            "command": command,
            "timeout_seconds": timeout_seconds,
            "verdict": "PENDING",
        }
        denial = _replay_command_denial(command)
        if denial:
            error = f"deterministic_replay_command_denied:{task_id}:{denial}"
            errors.append(error)
            task_report["verdict"] = "FAIL"
            task_report["error"] = error
            reports.append(task_report)
            continue

        work_dir = execution_root / task_id
        work_dir.mkdir(parents=True, exist_ok=True)
        try:
            completed = subprocess.run(
                _resolved_replay_command(command),
                cwd=work_dir,
                env=_replay_env(work_dir),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            error = f"deterministic_replay_timeout:{task_id}"
            errors.append(error)
            task_report.update(
                {
                    "verdict": "FAIL",
                    "error": error,
                    "stdout_tail": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
                    "stderr_tail": (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "",
                }
            )
            reports.append(task_report)
            continue

        task_report.update(
            {
                "returncode": completed.returncode,
                "stdout_tail": completed.stdout[-2000:],
                "stderr_tail": completed.stderr[-2000:],
            }
        )
        if completed.returncode != 0:
            error = f"deterministic_replay_command_failed:{task_id}:{completed.returncode}"
            errors.append(error)
            task_report["verdict"] = "FAIL"
            task_report["error"] = error
            reports.append(task_report)
            continue

        expected_shas = _task_artifact_sha_set(task)
        output_reports: list[dict[str, object]] = []
        for output in task.get("replay_outputs", []):
            try:
                output_path = _safe_output_path(work_dir, output)
            except ValueError:
                error = f"deterministic_replay_output_unsafe:{task_id}:{output}"
                errors.append(error)
                output_reports.append({"path": str(output), "verdict": "FAIL", "error": error})
                continue
            if not output_path.is_file():
                error = f"deterministic_replay_output_missing:{task_id}:{output}"
                errors.append(error)
                output_reports.append({"path": str(output), "verdict": "FAIL", "error": error})
                continue
            observed_sha = evidence_pack_writer._sha256_file(output_path)
            if observed_sha not in expected_shas:
                error = f"deterministic_replay_output_hash_mismatch:{task_id}:{output}"
                errors.append(error)
                output_reports.append(
                    {
                        "path": str(output),
                        "sha256": observed_sha,
                        "verdict": "FAIL",
                        "error": error,
                    }
                )
                continue
            output_reports.append({"path": str(output), "sha256": observed_sha, "verdict": "PASS"})
        task_report["outputs"] = output_reports
        task_report["verdict"] = (
            "PASS" if all(output.get("verdict") == "PASS" for output in output_reports) else "FAIL"
        )
        reports.append(task_report)
    return reports, errors


def replay_pack(
    path: Path,
    *,
    hmac_key: bytes | None = None,
    execute_deterministic: bool = False,
    deterministic_timeout_seconds: float = 5.0,
) -> dict[str, object]:
    verify = verify_pack(path, hmac_key=hmac_key)
    checks = {
        "verification": verify["verdict"],
        "event_task_coverage": "PENDING",
        "transcript_paths": "PENDING",
        "artifact_refs": "PENDING",
        "deterministic_non_llm_replay": "SKIPPED",
        "deterministic_command_execution": "SKIPPED",
    }
    errors: list[str] = list(verify.get("errors", []))
    deterministic_executions: list[dict[str, object]] = []

    with tempfile.TemporaryDirectory(prefix="ao-operator-evidence-pack-replay-") as tmp:
        scratch = Path(tmp)
        pack_root = _materialize_pack(path, scratch)
        manifest, _ = _load_manifest(pack_root)
        events = _read_events(pack_root)

        event_errors = _check_event_task_coverage(manifest, events)
        checks["event_task_coverage"] = "PASS" if not event_errors else "FAIL"
        errors.extend(event_errors)

        transcript_errors = _check_transcript_paths(pack_root, manifest)
        checks["transcript_paths"] = "PASS" if not transcript_errors else "FAIL"
        errors.extend(transcript_errors)

        artifact_ref_errors = _check_artifact_refs(pack_root, manifest)
        checks["artifact_refs"] = "PASS" if not artifact_ref_errors else "FAIL"
        errors.extend(artifact_ref_errors)

        deterministic_task_count, deterministic_errors = _check_deterministic_replay_declarations(
            pack_root, manifest
        )
        if deterministic_task_count:
            checks["deterministic_non_llm_replay"] = "PASS" if not deterministic_errors else "FAIL"
            errors.extend(deterministic_errors)
            deterministic_replay_note = (
                f"Validated {deterministic_task_count} deterministic non-LLM task "
                "declaration(s): replay_command and replay_outputs are present, "
                "and declared outputs resolve to content-addressed artifacts. "
                "Provider/LLM calls are not replayed."
            )
            if execute_deterministic and not deterministic_errors:
                deterministic_executions, execution_errors = _execute_deterministic_tasks(
                    manifest,
                    timeout_seconds=deterministic_timeout_seconds,
                    scratch=scratch,
                )
                checks["deterministic_command_execution"] = (
                    "PASS" if not execution_errors else "FAIL"
                )
                errors.extend(execution_errors)
        else:
            deterministic_replay_note = (
                "No profile-level deterministic task declarations are present in "
                "evidence-pack/v1; non-LLM rerun is skipped until profiles emit them."
            )
        return {
            "schema": "ao-operator/evidence-pack-replay/v1",
            "pack": str(path),
            "run_id": manifest.get("run_id"),
            "verdict": "PASS" if not errors else "FAIL",
            "checks": checks,
            "errors": errors,
            "verify": verify,
            "task_count": len(_task_ids(manifest)),
            "event_count": len(events),
            "deterministic_task_count": deterministic_task_count,
            "deterministic_replay_note": deterministic_replay_note,
            "deterministic_executions": deterministic_executions,
        }


def verify_pack(path: Path, *, hmac_key: bytes | None = None) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="ao-operator-evidence-pack-verify-") as tmp:
        pack_root = _materialize_pack(path, Path(tmp))
        manifest, manifest_bytes = _load_manifest(pack_root)
        checks = {"signature": "PENDING", "merkle_root": "PENDING", "artifact_shas": "PENDING"}
        errors: list[str] = []

        sig_status, sig_error = _verify_signature(pack_root, manifest, manifest_bytes, hmac_key)
        checks["signature"] = sig_status
        if sig_error:
            errors.append(sig_error)

        observed_root = evidence_pack_writer.merkle_root(evidence_pack_writer._relative_file_hashes(pack_root))
        expected_root = str(manifest.get("merkle_root", "")).removeprefix("sha256:")
        if observed_root == expected_root:
            checks["merkle_root"] = "PASS"
        else:
            checks["merkle_root"] = "FAIL"
            errors.append("merkle_root_mismatch")

        artifact_errors = _verify_artifacts(pack_root)
        checks["artifact_shas"] = "PASS" if not artifact_errors else "FAIL"
        errors.extend(artifact_errors)

        return {
            "schema": "ao-operator/evidence-pack-verify/v1",
            "pack": str(path),
            "run_id": manifest.get("run_id"),
            "verdict": "PASS" if not errors else "FAIL",
            "checks": checks,
            "errors": errors,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a AO Operator evidence pack")
    parser.add_argument("pack", type=Path)
    parser.add_argument("--hmac-key-hex")
    args = parser.parse_args(argv)

    hmac_key = bytes.fromhex(args.hmac_key_hex) if args.hmac_key_hex else None
    report = verify_pack(args.pack, hmac_key=hmac_key)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


def replay_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay a AO Operator evidence pack")
    parser.add_argument("pack", type=Path)
    parser.add_argument("--hmac-key-hex")
    parser.add_argument("--write-report", type=Path, help="Persist replay JSON to this path")
    parser.add_argument(
        "--execute-deterministic",
        action="store_true",
        help="Opt in to executing deterministic non-LLM replay commands",
    )
    parser.add_argument("--deterministic-timeout-seconds", type=float, default=5.0)
    args = parser.parse_args(argv)

    hmac_key = bytes.fromhex(args.hmac_key_hex) if args.hmac_key_hex else None
    report = replay_pack(
        args.pack,
        hmac_key=hmac_key,
        execute_deterministic=args.execute_deterministic,
        deterministic_timeout_seconds=args.deterministic_timeout_seconds,
    )
    report_json = json.dumps(report, indent=2, sort_keys=True)
    if args.write_report is not None:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(report_json + "\n", encoding="utf-8")
    print(report_json)
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
