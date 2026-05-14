"""Replay-backed v0.4 parallel-slice end-to-end checks."""
from __future__ import annotations

import json
from pathlib import Path

import auto_partition
import factory_run
import gate_r
import provider_record_replay as prr


def _role_contract(slug: str, role_id: str) -> dict[str, object]:
    role_artifact = f"run-artifacts/{slug}/roles/{role_id}.md"
    return {
        "id": role_id,
        "reads": [],
        "writes": [role_artifact],
        "skills": [],
        "is_mutator": role_id.startswith("implementer-slice"),
        "role_artifact": role_artifact,
        "allowed_artifacts": [role_artifact],
    }


def _write_gate_b(repo: Path, slug: str, role_ids: list[str], slices: list[dict[str, object]]) -> Path:
    roles = [_role_contract(slug, role_id) for role_id in role_ids]
    gate_b = repo / "run-artifacts" / slug / "gate-b.json"
    gate_b.parent.mkdir(parents=True, exist_ok=True)
    gate_b.write_text(
        json.dumps(
            {
                "schema": "ao-operator/gate-b/v1",
                "slug": slug,
                "verdict": "PASS",
                "spec": {
                    "schema": "ao-operator/gate-b/spec/v1",
                    "slug": slug,
                    "role_artifacts": {
                        role_id: f"run-artifacts/{slug}/roles/{role_id}.md"
                        for role_id in role_ids
                    },
                    "roles": roles,
                    "partition_slices": slices,
                },
                "partition": {
                    "schema": "ao-operator/gate-b/partition/v1",
                    "slices": slices,
                    "slice_count": len(slices),
                    "errors": [],
                    "verdict": "PASS",
                },
                "role_contracts": roles,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return gate_b


def _write_role(repo: Path, slug: str, role_id: str, *, result: str = "DONE", evidence: str = "- replay-backed\n") -> None:
    role = repo / "run-artifacts" / slug / "roles" / f"{role_id}.md"
    role.parent.mkdir(parents=True, exist_ok=True)
    role.write_text(
        f"""# {role_id} Role Artifact

Result: {result}
Artifact: run-artifacts/{slug}/roles/{role_id}.md
Evidence:
{evidence.rstrip()}
Concerns:
- none
Blocker: none
""",
        encoding="utf-8",
    )


def _write_patch_bundle(repo: Path, slug: str, task_id: str, write_path: str) -> None:
    patches = repo / "run-artifacts" / slug / "patches"
    patches.mkdir(parents=True, exist_ok=True)
    diff = "\n".join(
        [
            f"diff --git a/{write_path} b/{write_path}",
            "new file mode 100644",
            "index 0000000..1111111",
            "--- /dev/null",
            f"+++ b/{write_path}",
            "@@ -0,0 +1 @@",
            f"+{task_id}",
            "",
        ]
    )
    (patches / f"{task_id}.patch").write_text(diff, encoding="utf-8")
    (patches / f"{task_id}.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "patch": f"run-artifacts/{slug}/patches/{task_id}.patch",
                "raw_events": f"run-artifacts/{slug}/patches/{task_id}-events.txt",
                "status_result": "DONE",
                "status_captured": True,
                "diff_exit": 0,
                "diff_bytes": len(diff.encode("utf-8")),
                "scoped_writes": [write_path],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _record_and_replay(repo: Path, slug: str, task_id: str, response: str, capsys) -> str:
    prompt = repo / "run-artifacts" / slug / "prompts" / f"{task_id}.md"
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text(f"Provider prompt for {task_id}\n", encoding="utf-8")
    response_file = repo / "run-artifacts" / slug / "responses" / f"{task_id}.txt"
    response_file.parent.mkdir(parents=True, exist_ok=True)
    response_file.write_text(response, encoding="utf-8")
    recording = repo / "run-artifacts" / slug / "provider-recording.jsonl"

    assert prr.main(
        [
            "record",
            "--recording",
            str(recording),
            "--provider",
            "codex",
            "--task-id",
            task_id,
            "--prompt-file",
            str(prompt),
            "--response-file",
            str(response_file),
            "--param",
            "model=replay",
        ]
    ) == 0
    capsys.readouterr()
    assert prr.main(
        [
            "replay",
            "--recording",
            str(recording),
            "--provider",
            "codex",
            "--task-id",
            task_id,
            "--prompt-file",
            str(prompt),
            "--param",
            "model=replay",
            "--ao-events",
        ]
    ) == 0
    return capsys.readouterr().out


def _materialize_replayed_parallel_run(repo: Path, slug: str, capsys) -> tuple[Path, list[dict[str, object]]]:
    slices = auto_partition.partition(
        brief="Scope: write docs/final/a.md and docs/final/b.md",
        scoped_writes=["docs/final/a.md", "docs/final/b.md"],
    )
    tasks = factory_run.expand_slice_topology(
        factory_run.BASELINE_TASKS,
        num_slices=len(slices),
        slice_specs=slices,
    )
    task_ids = [str(task["id"]) for task in tasks]
    assert {"implementer-slice-1", "implementer-slice-2", "reviewer-slice-1", "reviewer-slice-2"} <= set(task_ids)

    role_ids = [
        "implementer-slice-1",
        "reviewer-slice-1",
        "implementer-slice-2",
        "reviewer-slice-2",
        "integrator",
        "evaluator-closer",
    ]
    gate_b = _write_gate_b(repo, slug, role_ids, slices)

    replayed_events = []
    for task_id in role_ids:
        replayed_events.append(_record_and_replay(repo, slug, task_id, f"Result: DONE\nArtifact: {task_id}\n", capsys))
    assert all("task.completed" in events for events in replayed_events)

    for item in slices:
        slice_id = int(item["slice_id"])
        implementer = f"implementer-slice-{slice_id}"
        reviewer = f"reviewer-slice-{slice_id}"
        write_path = str(item["writes"][0])
        _write_role(repo, slug, implementer)
        _write_role(repo, slug, reviewer)
        _write_patch_bundle(repo, slug, implementer, write_path)
    _write_role(
        repo,
        slug,
        "integrator",
        evidence=(
            "- slice-1 implementer-slice-1 reviewer-slice-1 -> docs/final/a.md accepted\n"
            "- slice-2 implementer-slice-2 reviewer-slice-2 -> docs/final/b.md accepted\n"
        ),
    )
    _write_role(repo, slug, "evaluator-closer")
    return gate_b, slices


def test_parallel_slice_replay_e2e_passes_fanout_and_rejoin(tmp_path: Path, capsys):
    slug = "parallel-slice-replay"
    gate_b, slices = _materialize_replayed_parallel_run(tmp_path, slug, capsys)

    report = gate_r.run_gate(repo=tmp_path, slug=slug, gate_b_path=gate_b)

    assert len(slices) == 2
    assert report["verdict"] == "PASS", report["errors"]
    mapping_checks = [check for check in report["checks"] if str(check["id"]).startswith("slice_final_artifact_mapping:")]
    assert {tuple(check["final_artifacts"]) for check in mapping_checks} == {
        ("docs/final/a.md",),
        ("docs/final/b.md",),
    }


def test_parallel_slice_replay_e2e_fails_closed_on_integrator_drift(tmp_path: Path, capsys):
    slug = "parallel-slice-replay-drift"
    gate_b, _ = _materialize_replayed_parallel_run(tmp_path, slug, capsys)
    _write_role(
        tmp_path,
        slug,
        "integrator",
        evidence="- slice-1 implementer-slice-1 reviewer-slice-1 -> docs/final/a.md accepted\n",
    )

    report = gate_r.run_gate(repo=tmp_path, slug=slug, gate_b_path=gate_b)

    assert report["verdict"] == "FAIL"
    assert any("slice-2: integrator disposition missing" in error for error in report["errors"])
