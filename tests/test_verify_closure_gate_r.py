from __future__ import annotations

import json
from pathlib import Path

import verify_closure


def test_gate_r_contract_evidence_discovers_committed_gate_b_failure(tmp_path: Path):
    slug = "demo"
    status = tmp_path / "run-artifacts" / slug
    roles = status / "roles"
    roles.mkdir(parents=True)
    (status / "gate-b.json").write_text(
        json.dumps(
            {
                "schema": "ao-operator/gate-b/v1",
                "slug": slug,
                "verdict": "PASS",
                "spec": {
                    "schema": "ao-operator/gate-b/spec/v1",
                    "slug": slug,
                    "role_artifacts": {
                        "implementer-slice": f"run-artifacts/{slug}/roles/implementer-slice.md",
                        "reviewer-slice": f"run-artifacts/{slug}/roles/reviewer-slice.md",
                        "integrator": f"run-artifacts/{slug}/roles/integrator.md",
                    },
                    "roles": [
                        {
                            "id": role_id,
                            "allowed_artifacts": [f"run-artifacts/{slug}/roles/{role_id}.md"],
                        }
                        for role_id in ("implementer-slice", "reviewer-slice", "integrator")
                    ],
                    "partition_slices": [
                        {
                            "id": "slice-1",
                            "slice_id": 1,
                            "reads": ["docs/specs/demo-spec.md"],
                            "writes": ["docs/final/a.md"],
                            "verification": ["pytest"],
                            "merge_owner": "integrator",
                            "rejoin_artifact": f"run-artifacts/{slug}/roles/integrator.md",
                        }
                    ],
                },
                "partition": {"slices": []},
                "role_contracts": [],
            }
        ),
        encoding="utf-8",
    )
    for role_id in ("implementer-slice", "reviewer-slice", "integrator"):
        (roles / f"{role_id}.md").write_text(
            f"Result: DONE\nArtifact: run-artifacts/{slug}/roles/{role_id}.md\n",
            encoding="utf-8",
        )

    result = verify_closure.gate_r_contract_evidence(tmp_path)

    assert result["verdict"] == "FAIL"
    assert any("missing patch bundle" in detail for detail in result["details"])


def test_gate_r_contract_evidence_skips_when_no_gate_b_exists(tmp_path: Path):
    result = verify_closure.gate_r_contract_evidence(tmp_path)

    assert result == {"verdict": "PASS", "details": [], "reports": []}
