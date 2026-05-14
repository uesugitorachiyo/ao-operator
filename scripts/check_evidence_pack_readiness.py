#!/usr/bin/env python3
"""Deterministic evidence-pack generation and replay readiness gate."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import evidence_pack_verify
import evidence_pack_writer

SCHEMA = "ao-operator/evidence-pack-readiness/v1"
HMAC_KEY = b"ao-operator-readiness-key"


def _inputs(work: Path) -> evidence_pack_writer.RunInputs:
    artifact = work / "artifact.txt"
    artifact.write_text("evidence pack readiness artifact\n", encoding="utf-8")
    return evidence_pack_writer.RunInputs(
        run_id="readinessfeed01",
        factory_version="readiness",
        ao_runtime_version="readiness",
        created_at="2026-05-11T18:00:00+00:00",
        completed_at="2026-05-11T18:00:01+00:00",
        operator=evidence_pack_writer.OperatorRecord(
            host_fingerprint="sha256:readiness",
            user_label="readiness-host",
        ),
        profile=evidence_pack_writer.ProfileRecord(
            name="readiness",
            version="v1",
            policy_digest="sha256:readiness",
        ),
        providers=[
            evidence_pack_writer.ProviderRecord(
                role="intake",
                name="codex",
                version="readiness",
            )
        ],
        tasks=[
            evidence_pack_writer.TaskRecord(
                task_id="intake",
                role="planner-intake",
                status="completed",
                started_at="2026-05-11T18:00:00+00:00",
                completed_at="2026-05-11T18:00:01+00:00",
                deterministic=True,
                replay_command=[
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path('artifact.txt').write_text('evidence pack readiness artifact\\n', encoding='utf-8')",
                ],
                replay_outputs=["artifact.txt"],
            )
        ],
        events=[
            {
                "ts": "2026-05-11T18:00:00+00:00",
                "trace_id": "0af7651916cd43dd8448eb211c80319c",
                "span_id": "b7ad6b7169203331",
                "type": "task.completed",
                "task_id": "intake",
                "attrs": {},
            }
        ],
        transcripts={
            "intake": [
                {
                    "role": "assistant",
                    "content": "readiness",
                    "ts": "2026-05-11T18:00:00+00:00",
                }
            ]
        },
        artifact_paths={"intake": [artifact]},
    )


def check_readiness(work_dir: Path) -> dict[str, object]:
    work_dir.mkdir(parents=True, exist_ok=True)
    pack = evidence_pack_writer.write_pack(
        _inputs(work_dir),
        work_dir / "packs",
        evidence_pack_writer.HMACSigner(HMAC_KEY),
    )
    archive = evidence_pack_writer.write_tar_zst(pack, work_dir / "archives")
    verify = evidence_pack_verify.verify_pack(archive, hmac_key=HMAC_KEY)
    replay = evidence_pack_verify.replay_pack(
        archive,
        hmac_key=HMAC_KEY,
        execute_deterministic=True,
    )
    return {
        "schema": SCHEMA,
        "verdict": "PASS" if verify["verdict"] == "PASS" and replay["verdict"] == "PASS" else "FAIL",
        "pack": str(pack),
        "archive": str(archive),
        "verify": verify,
        "replay": replay,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check evidence-pack generation and replay readiness")
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.work_dir:
        report = check_readiness(args.work_dir)
    else:
        with tempfile.TemporaryDirectory(prefix="ao-operator-evidence-pack-readiness-") as tmp:
            report = check_readiness(Path(tmp))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(report["verdict"])
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
