from __future__ import annotations

import json
from pathlib import Path

import gate_r


def _gate_b(path: Path, slug: str, role_ids: list[str], partition_slices: list[dict] | None = None) -> Path:
    roles = [
        {
            "id": role_id,
            "reads": [],
            "writes": [f"run-artifacts/{slug}/roles/{role_id}.md"],
            "skills": [],
            "is_mutator": False,
            "role_artifact": f"run-artifacts/{slug}/roles/{role_id}.md",
            "allowed_artifacts": [f"run-artifacts/{slug}/roles/{role_id}.md"],
        }
        for role_id in role_ids
    ]
    path.write_text(
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
                    "partition_slices": partition_slices or [],
                },
                "partition": {
                    "schema": "ao-operator/gate-b/partition/v1",
                    "slices": partition_slices or [],
                    "slice_count": len(partition_slices or []),
                    "errors": [],
                    "verdict": "PASS",
                },
                "role_contracts": roles,
            }
        ),
        encoding="utf-8",
    )
    return path


def _patch_bundle(repo: Path, slug: str, task_id: str, diff: str = "diff --git a/a b/a\n") -> None:
    patches = repo / "run-artifacts" / slug / "patches"
    patches.mkdir(parents=True, exist_ok=True)
    patch = patches / f"{task_id}.patch"
    patch.write_text(diff, encoding="utf-8")
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
                "scoped_writes": [],
            }
        ),
        encoding="utf-8",
    )


def _role_artifact(
    repo: Path,
    slug: str,
    role_id: str,
    result: str = "DONE",
    artifact: str | None = None,
    extra_evidence: str = "",
) -> Path:
    path = repo / "run-artifacts" / slug / "roles" / f"{role_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    artifact = artifact or f"run-artifacts/{slug}/roles/{role_id}.md"
    path.write_text(
        f"""Result: {result}
Artifact: {artifact}
Evidence:
- synthetic
{extra_evidence}
Concerns:
- none
Blocker: none
""",
        encoding="utf-8",
    )
    return path


def test_gate_r_passes_when_declared_role_artifact_is_done(tmp_path: Path):
    gate_b_path = _gate_b(tmp_path / "gate-b.json", "demo", ["planner-intake"])
    _role_artifact(tmp_path, "demo", "planner-intake")

    report = gate_r.run_gate(repo=tmp_path, slug="demo", gate_b_path=gate_b_path)

    assert report["verdict"] == "PASS"


def test_gate_r_fails_unexpected_role_artifact(tmp_path: Path):
    gate_b_path = _gate_b(tmp_path / "gate-b.json", "demo", ["planner-intake"])
    _role_artifact(tmp_path, "demo", "planner-intake")
    _role_artifact(tmp_path, "demo", "rogue")

    report = gate_r.run_gate(repo=tmp_path, slug="demo", gate_b_path=gate_b_path)

    assert report["verdict"] == "FAIL"
    assert any("unexpected role artifact" in error for error in report["errors"])


def test_gate_r_fails_blocked_role_result(tmp_path: Path):
    gate_b_path = _gate_b(tmp_path / "gate-b.json", "demo", ["planner-intake"])
    _role_artifact(tmp_path, "demo", "planner-intake", result="BLOCKED")

    report = gate_r.run_gate(repo=tmp_path, slug="demo", gate_b_path=gate_b_path)

    assert report["verdict"] == "FAIL"
    assert any("role returned BLOCKED" in error for error in report["errors"])


def test_gate_r_fails_artifact_outside_gate_b_contract(tmp_path: Path):
    gate_b_path = _gate_b(tmp_path / "gate-b.json", "demo", ["planner-intake"])
    _role_artifact(
        tmp_path,
        "demo",
        "planner-intake",
        artifact="run-artifacts/demo/roles/undeclared.md",
    )

    report = gate_r.run_gate(repo=tmp_path, slug="demo", gate_b_path=gate_b_path)

    assert report["verdict"] == "FAIL"
    assert any("artifact drift outside Gate B contract" in error for error in report["errors"])


def test_gate_r_passes_slice_integrator_contract(tmp_path: Path):
    slices = [
        {
            "id": "slice-1",
            "slice_id": 1,
            "reads": ["docs/specs/demo-spec.md"],
            "writes": ["docs/final/a.md"],
            "verification": ["pytest"],
            "merge_owner": "integrator",
            "rejoin_artifact": "run-artifacts/demo/roles/integrator.md",
        },
        {
            "id": "slice-2",
            "slice_id": 2,
            "reads": ["docs/specs/demo-spec.md"],
            "writes": ["docs/final/b.md"],
            "verification": ["pytest"],
            "merge_owner": "integrator",
            "rejoin_artifact": "run-artifacts/demo/roles/integrator.md",
        },
    ]
    role_ids = [
        "implementer-slice-1",
        "reviewer-slice-1",
        "implementer-slice-2",
        "reviewer-slice-2",
        "integrator",
        "evaluator-closer",
    ]
    gate_b_path = _gate_b(tmp_path / "gate-b.json", "demo", role_ids, slices)
    for task_id in ("implementer-slice-1", "implementer-slice-2"):
        _role_artifact(tmp_path, "demo", task_id)
        _patch_bundle(tmp_path, "demo", task_id)
    _role_artifact(tmp_path, "demo", "reviewer-slice-1")
    _role_artifact(tmp_path, "demo", "reviewer-slice-2")
    _role_artifact(
        tmp_path,
        "demo",
        "integrator",
        extra_evidence=(
            "- slice-1 implementer-slice-1 reviewer-slice-1 -> docs/final/a.md accepted\n"
            "- slice-2 implementer-slice-2 reviewer-slice-2 -> docs/final/b.md accepted"
        ),
    )
    _role_artifact(tmp_path, "demo", "evaluator-closer")

    report = gate_r.run_gate(repo=tmp_path, slug="demo", gate_b_path=gate_b_path)

    assert report["verdict"] == "PASS", report["errors"]
    assert any(check["id"] == "slice_final_artifact_mapping:slice-1" for check in report["checks"])


def test_gate_r_fails_missing_slice_patch_bundle(tmp_path: Path):
    slices = [
        {
            "id": "slice-1",
            "slice_id": 1,
            "reads": ["docs/specs/demo-spec.md"],
            "writes": ["docs/final/a.md"],
            "verification": ["pytest"],
            "merge_owner": "integrator",
            "rejoin_artifact": "run-artifacts/demo/roles/integrator.md",
        }
    ]
    role_ids = ["implementer-slice", "reviewer-slice", "integrator"]
    gate_b_path = _gate_b(tmp_path / "gate-b.json", "demo", role_ids, slices)
    _role_artifact(tmp_path, "demo", "implementer-slice")
    _role_artifact(tmp_path, "demo", "reviewer-slice")
    _role_artifact(
        tmp_path,
        "demo",
        "integrator",
        extra_evidence="- slice-1 implementer-slice reviewer-slice -> docs/final/a.md accepted",
    )

    report = gate_r.run_gate(repo=tmp_path, slug="demo", gate_b_path=gate_b_path)

    assert report["verdict"] == "FAIL"
    assert any("missing patch bundle" in error for error in report["errors"])


def test_gate_r_fails_missing_integrator_disposition(tmp_path: Path):
    slices = [
        {
            "id": "slice-1",
            "slice_id": 1,
            "reads": ["docs/specs/demo-spec.md"],
            "writes": ["docs/final/a.md"],
            "verification": ["pytest"],
            "merge_owner": "integrator",
            "rejoin_artifact": "run-artifacts/demo/roles/integrator.md",
        }
    ]
    role_ids = ["implementer-slice", "reviewer-slice", "integrator"]
    gate_b_path = _gate_b(tmp_path / "gate-b.json", "demo", role_ids, slices)
    _role_artifact(tmp_path, "demo", "implementer-slice")
    _patch_bundle(tmp_path, "demo", "implementer-slice")
    _role_artifact(tmp_path, "demo", "reviewer-slice")
    _role_artifact(tmp_path, "demo", "integrator", extra_evidence="- integrated something else")

    report = gate_r.run_gate(repo=tmp_path, slug="demo", gate_b_path=gate_b_path)

    assert report["verdict"] == "FAIL"
    assert any("integrator disposition missing" in error for error in report["errors"])


def test_gate_r_fails_slice_without_final_artifact_mapping(tmp_path: Path):
    slices = [
        {
            "id": "slice-1",
            "slice_id": 1,
            "reads": ["docs/specs/demo-spec.md"],
            "writes": [],
            "verification": ["pytest"],
            "merge_owner": "integrator",
            "rejoin_artifact": "run-artifacts/demo/roles/integrator.md",
        }
    ]
    role_ids = ["implementer-slice", "reviewer-slice", "integrator"]
    gate_b_path = _gate_b(tmp_path / "gate-b.json", "demo", role_ids, slices)
    _role_artifact(tmp_path, "demo", "implementer-slice")
    _patch_bundle(tmp_path, "demo", "implementer-slice")
    _role_artifact(tmp_path, "demo", "reviewer-slice")
    _role_artifact(
        tmp_path,
        "demo",
        "integrator",
        extra_evidence="- slice-1 implementer-slice reviewer-slice accepted",
    )

    report = gate_r.run_gate(repo=tmp_path, slug="demo", gate_b_path=gate_b_path)

    assert report["verdict"] == "FAIL"
    assert any("no final artifact mapping" in error for error in report["errors"])
