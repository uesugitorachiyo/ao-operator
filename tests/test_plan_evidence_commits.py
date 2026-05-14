from __future__ import annotations

import json
import subprocess

import plan_evidence_commits


def entry(path: str, status: str = "??") -> plan_evidence_commits.StatusEntry:
    return plan_evidence_commits.StatusEntry(status=status, path=path)


def run_git(root, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout


def write_file(root, path: str, body: str = "content\n") -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


def test_build_plan_groups_success_diagnostics_and_scratch_paths():
    plan = plan_evidence_commits.build_plan(
        [
            entry("scripts/factory_run.py", " M"),
            entry("examples/remote-transfer-v2-stress/operator-slices.json"),
            entry("run-artifacts/remote-transfer-v2-stress/prompts/identity-factory.md", " M"),
            entry("run-artifacts/remote-transfer-v2-stress-live/prompts/identity-factory.md"),
            entry("run-artifacts/remote-transfer-v2-stress/failure-snapshots/ao-home-429/events.jsonl"),
            entry("run-artifacts/remote-transfer-v2-stress/operator-runs/20260506-023721.json"),
            entry("run-artifacts/test-operator/operator-runs/report.json"),
        ],
        generated_at="2026-05-06T00:00:00+00:00",
    )

    groups = {group["id"]: group for group in plan["groups"]}
    assert plan["verdict"] == "PASS"
    assert groups["runtime-guardrails-and-tests"]["count"] == 1
    assert groups["operator-sdd-and-manifest"]["count"] == 1
    assert groups["large-dry-run-materialization"]["count"] == 1
    assert groups["bounded-live-profile-dry-run"]["count"] == 1
    assert groups["failed-live-diagnostics"]["count"] == 1
    assert groups["operator-run-reports"]["count"] == 1
    assert groups["scratch-excluded"]["commit_allowed"] is False
    assert "successful live evidence" in plan["warnings"][0]


def test_build_plan_fails_on_unclassified_paths():
    plan = plan_evidence_commits.build_plan([entry("unexpected/file.txt")])

    assert plan["verdict"] == "FAIL"
    assert plan["errors"] == ["unclassified path: unexpected/file.txt"]


def test_write_plan_uses_commit_readiness_directory(tmp_path):
    plan = plan_evidence_commits.build_plan([], slug="slug", generated_at="2026-05-06T00:00:00+00:00")

    path = plan_evidence_commits.write_plan(plan, slug="slug", root=tmp_path)

    assert path.parent == tmp_path / "run-artifacts" / "slug" / "commit-readiness"
    assert json.loads(path.read_text(encoding="utf-8"))["schema"] == "ao-operator/commit-readiness/v1"


def test_build_staging_plan_orders_runtime_and_operator_first():
    readiness = plan_evidence_commits.build_plan(
        [
            entry("scripts/factory_run.py", " M"),
            entry("examples/remote-transfer-v2-stress/operator-slices.json"),
            entry("run-artifacts/remote-transfer-v2-stress/failure-snapshots/ao-home-429/events.jsonl"),
        ],
        generated_at="2026-05-06T00:00:00+00:00",
    )

    staging = plan_evidence_commits.build_staging_plan(
        readiness,
        slug="remote-transfer-v2-stress",
        generated_at="2026-05-06T00:01:00+00:00",
        plan_dir="run-artifacts/remote-transfer-v2-stress/staging-plans/test",
    )

    assert staging["verdict"] == "PASS"
    assert [batch["group_id"] for batch in staging["batches"]] == [
        "runtime-guardrails-and-tests",
        "operator-sdd-and-manifest",
        "failed-live-diagnostics",
    ]
    assert staging["batches"][0]["stage_command"].endswith("01-runtime-guardrails-and-tests.pathspec")
    assert staging["batches"][-1]["success_evidence"] is False
    assert "diagnostic-only" in staging["batches"][-1]["notes"][0]


def test_write_staging_plan_writes_summary_and_pathspecs(tmp_path):
    readiness = plan_evidence_commits.build_plan(
        [
            entry("scripts/factory_run.py", " M"),
            entry("examples/remote-transfer-v2-stress/operator-slices.json"),
        ],
        generated_at="2026-05-06T00:00:00+00:00",
    )
    staging = plan_evidence_commits.build_staging_plan(
        readiness,
        slug="remote-transfer-v2-stress",
        generated_at="2026-05-06T00:01:00+00:00",
    )

    summary = plan_evidence_commits.write_staging_plan(staging, slug="remote-transfer-v2-stress", root=tmp_path)

    data = json.loads(summary.read_text(encoding="utf-8"))
    assert data["schema"] == "ao-operator/staged-commit-plan/v1"
    assert len(data["batches"]) == 2
    for batch in data["batches"]:
        pathspec = tmp_path / batch["pathspec_file"]
        assert pathspec.is_file()
        assert pathspec.read_text(encoding="utf-8").strip()


def test_staging_plan_artifacts_are_operator_run_reports():
    assert (
        plan_evidence_commits.classify_path(
            "run-artifacts/remote-transfer-v2-stress/staging-plans/20260506-000000/staging-plan.json"
        )
        == "operator-run-reports"
    )


def test_verify_staging_plan_accepts_clean_pathspecs(tmp_path):
    readiness = plan_evidence_commits.build_plan(
        [
            entry("scripts/factory_run.py", " M"),
            entry("examples/remote-transfer-v2-stress/operator-slices.json"),
            entry("run-artifacts/remote-transfer-v2-stress/failure-snapshots/ao-home-429/events.jsonl"),
        ],
        generated_at="2026-05-06T00:00:00+00:00",
    )
    staging = plan_evidence_commits.build_staging_plan(
        readiness,
        slug="remote-transfer-v2-stress",
        generated_at="2026-05-06T00:01:00+00:00",
    )
    summary = plan_evidence_commits.write_staging_plan(staging, slug="remote-transfer-v2-stress", root=tmp_path)

    result = plan_evidence_commits.verify_staging_plan(summary, root=tmp_path)

    assert result["verdict"] == "PASS"
    assert result["errors"] == []


def test_verify_staging_plan_rejects_success_batch_with_failed_live_path(tmp_path):
    readiness = plan_evidence_commits.build_plan(
        [
            entry("scripts/factory_run.py", " M"),
            entry("examples/remote-transfer-v2-stress/operator-slices.json"),
            entry("run-artifacts/remote-transfer-v2-stress/failure-snapshots/ao-home-429/events.jsonl"),
        ],
        generated_at="2026-05-06T00:00:00+00:00",
    )
    staging = plan_evidence_commits.build_staging_plan(
        readiness,
        slug="remote-transfer-v2-stress",
        generated_at="2026-05-06T00:01:00+00:00",
    )
    summary = plan_evidence_commits.write_staging_plan(staging, slug="remote-transfer-v2-stress", root=tmp_path)
    data = json.loads(summary.read_text(encoding="utf-8"))
    data["batches"][0]["paths"].append("run-artifacts/remote-transfer-v2-stress/failure-snapshots/ao-home-429/events.jsonl")
    data["batches"][0]["path_count"] += 1
    summary.write_text(json.dumps(data), encoding="utf-8")
    pathspec = tmp_path / data["batches"][0]["pathspec_file"]
    with pathspec.open("a", encoding="utf-8") as handle:
        handle.write("run-artifacts/remote-transfer-v2-stress/failure-snapshots/ao-home-429/events.jsonl\n")

    result = plan_evidence_commits.verify_staging_plan(summary, root=tmp_path)

    assert result["verdict"] == "FAIL"
    assert any("success batch includes failed-live diagnostics" in error for error in result["errors"])


def test_verify_staging_plan_rejects_failed_live_success_flag(tmp_path):
    readiness = plan_evidence_commits.build_plan(
        [
            entry("scripts/factory_run.py", " M"),
            entry("examples/remote-transfer-v2-stress/operator-slices.json"),
            entry("run-artifacts/remote-transfer-v2-stress/failure-snapshots/ao-home-429/events.jsonl"),
        ],
        generated_at="2026-05-06T00:00:00+00:00",
    )
    staging = plan_evidence_commits.build_staging_plan(
        readiness,
        slug="remote-transfer-v2-stress",
        generated_at="2026-05-06T00:01:00+00:00",
    )
    summary = plan_evidence_commits.write_staging_plan(staging, slug="remote-transfer-v2-stress", root=tmp_path)
    data = json.loads(summary.read_text(encoding="utf-8"))
    failed_live = next(batch for batch in data["batches"] if batch["group_id"] == "failed-live-diagnostics")
    failed_live["success_evidence"] = True
    summary.write_text(json.dumps(data), encoding="utf-8")

    result = plan_evidence_commits.verify_staging_plan(summary, root=tmp_path)

    assert result["verdict"] == "FAIL"
    assert "failed-live-diagnostics batch must have success_evidence=false" in result["errors"]


def test_verify_staging_plan_rejects_pathspec_mismatch(tmp_path):
    readiness = plan_evidence_commits.build_plan(
        [
            entry("scripts/factory_run.py", " M"),
            entry("examples/remote-transfer-v2-stress/operator-slices.json"),
            entry("run-artifacts/remote-transfer-v2-stress/failure-snapshots/ao-home-429/events.jsonl"),
        ],
        generated_at="2026-05-06T00:00:00+00:00",
    )
    staging = plan_evidence_commits.build_staging_plan(
        readiness,
        slug="remote-transfer-v2-stress",
        generated_at="2026-05-06T00:01:00+00:00",
    )
    summary = plan_evidence_commits.write_staging_plan(staging, slug="remote-transfer-v2-stress", root=tmp_path)
    data = json.loads(summary.read_text(encoding="utf-8"))
    pathspec = tmp_path / data["batches"][0]["pathspec_file"]
    pathspec.write_text("", encoding="utf-8")

    result = plan_evidence_commits.verify_staging_plan(summary, root=tmp_path)

    assert result["verdict"] == "FAIL"
    assert any("pathspec entries do not match" in error for error in result["errors"])


def test_rehearse_staging_plan_uses_temp_index_and_keeps_diagnostics_out(tmp_path):
    run_git(tmp_path, "init")
    write_file(tmp_path, "scripts/factory_run.py", "base\n")
    write_file(tmp_path, "examples/remote-transfer-v2-stress/operator-slices.json", "{}\n")
    write_file(tmp_path, "run-artifacts/remote-transfer-v2-stress/failure-snapshots/ao-home-429/events.jsonl", "{}\n")
    run_git(tmp_path, "add", ".")
    run_git(tmp_path, "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "base")
    write_file(tmp_path, "scripts/factory_run.py", "changed\n")
    write_file(tmp_path, "examples/remote-transfer-v2-stress/operator-slices.json", "{\"changed\": true}\n")
    write_file(tmp_path, "run-artifacts/remote-transfer-v2-stress/failure-snapshots/ao-home-429/events.jsonl", "{\"failed\": true}\n")
    readiness = plan_evidence_commits.build_plan(
        [
            entry("scripts/factory_run.py", " M"),
            entry("examples/remote-transfer-v2-stress/operator-slices.json", " M"),
            entry("run-artifacts/remote-transfer-v2-stress/failure-snapshots/ao-home-429/events.jsonl", " M"),
        ],
        generated_at="2026-05-06T00:00:00+00:00",
    )
    staging = plan_evidence_commits.build_staging_plan(
        readiness,
        slug="remote-transfer-v2-stress",
        generated_at="2026-05-06T00:01:00+00:00",
    )
    summary = plan_evidence_commits.write_staging_plan(staging, slug="remote-transfer-v2-stress", root=tmp_path)

    result = plan_evidence_commits.rehearse_staging_plan(
        summary,
        group_ids=["runtime-guardrails-and-tests", "operator-sdd-and-manifest"],
        root=tmp_path,
    )

    assert result["verdict"] == "PASS"
    assert result["real_index_untouched"] is True
    assert result["expected_path_count"] == 2
    assert result["rehearsed_staged_count"] == 2
    assert result["failed_live_diagnostic_paths"] == 0
    assert run_git(tmp_path, "diff", "--cached", "--name-only") == ""


def test_rehearse_staging_plan_refuses_diagnostic_batch(tmp_path):
    run_git(tmp_path, "init")
    write_file(tmp_path, "scripts/factory_run.py", "base\n")
    write_file(tmp_path, "examples/remote-transfer-v2-stress/operator-slices.json", "{}\n")
    write_file(tmp_path, "run-artifacts/remote-transfer-v2-stress/failure-snapshots/ao-home-429/events.jsonl", "{}\n")
    run_git(tmp_path, "add", ".")
    run_git(tmp_path, "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "base")
    write_file(tmp_path, "run-artifacts/remote-transfer-v2-stress/failure-snapshots/ao-home-429/events.jsonl", "{\"failed\": true}\n")
    readiness = plan_evidence_commits.build_plan(
        [
            entry("scripts/factory_run.py", " M"),
            entry("examples/remote-transfer-v2-stress/operator-slices.json", " M"),
            entry("run-artifacts/remote-transfer-v2-stress/failure-snapshots/ao-home-429/events.jsonl", " M"),
        ],
        generated_at="2026-05-06T00:00:00+00:00",
    )
    staging = plan_evidence_commits.build_staging_plan(
        readiness,
        slug="remote-transfer-v2-stress",
        generated_at="2026-05-06T00:01:00+00:00",
    )
    summary = plan_evidence_commits.write_staging_plan(staging, slug="remote-transfer-v2-stress", root=tmp_path)

    result = plan_evidence_commits.rehearse_staging_plan(
        summary,
        group_ids=["failed-live-diagnostics"],
        root=tmp_path,
    )

    assert result["verdict"] == "FAIL"
    assert any("refuses non-success evidence batches" in error for error in result["errors"])


def test_review_staging_batch_reports_exact_pathspec_without_staging(tmp_path):
    run_git(tmp_path, "init")
    write_file(tmp_path, "scripts/factory_run.py", "base\n")
    write_file(tmp_path, "scripts/plan_evidence_commits.py", "base\n")
    write_file(tmp_path, "examples/remote-transfer-v2-stress/operator-slices.json", "{}\n")
    write_file(tmp_path, "run-artifacts/remote-transfer-v2-stress/failure-snapshots/ao-home-429/events.jsonl", "{}\n")
    run_git(tmp_path, "add", ".")
    run_git(tmp_path, "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "base")
    write_file(tmp_path, "scripts/factory_run.py", "changed\n")
    write_file(tmp_path, "scripts/plan_evidence_commits.py", "changed\n")
    write_file(tmp_path, "examples/remote-transfer-v2-stress/operator-slices.json", "{\"changed\": true}\n")
    write_file(tmp_path, "run-artifacts/remote-transfer-v2-stress/failure-snapshots/ao-home-429/events.jsonl", "{\"failed\": true}\n")
    readiness = plan_evidence_commits.build_plan(
        [
            entry("scripts/factory_run.py", " M"),
            entry("scripts/plan_evidence_commits.py", " M"),
            entry("examples/remote-transfer-v2-stress/operator-slices.json", " M"),
            entry("run-artifacts/remote-transfer-v2-stress/failure-snapshots/ao-home-429/events.jsonl", " M"),
        ],
        generated_at="2026-05-06T00:00:00+00:00",
    )
    staging = plan_evidence_commits.build_staging_plan(
        readiness,
        slug="remote-transfer-v2-stress",
        generated_at="2026-05-06T00:01:00+00:00",
    )
    summary = plan_evidence_commits.write_staging_plan(staging, slug="remote-transfer-v2-stress", root=tmp_path)

    result = plan_evidence_commits.review_staging_batch(
        summary,
        group_id="runtime-guardrails-and-tests",
        root=tmp_path,
    )

    assert result["verdict"] == "PASS"
    assert result["pathspec_entries"] == ["scripts/factory_run.py", "scripts/plan_evidence_commits.py"]
    assert result["stage_command"].endswith("01-runtime-guardrails-and-tests.pathspec")
    assert "git diff --cached --name-only" in result["verification_commands"]
    assert run_git(tmp_path, "diff", "--cached", "--name-only") == ""


def test_review_staging_batch_refuses_diagnostic_batch(tmp_path):
    readiness = plan_evidence_commits.build_plan(
        [entry("run-artifacts/remote-transfer-v2-stress/failure-snapshots/ao-home-429/events.jsonl")],
        generated_at="2026-05-06T00:00:00+00:00",
    )
    staging = plan_evidence_commits.build_staging_plan(
        readiness,
        slug="remote-transfer-v2-stress",
        generated_at="2026-05-06T00:01:00+00:00",
    )
    summary = plan_evidence_commits.write_staging_plan(staging, slug="remote-transfer-v2-stress", root=tmp_path)

    result = plan_evidence_commits.review_staging_batch(
        summary,
        group_id="failed-live-diagnostics",
        root=tmp_path,
    )

    assert result["verdict"] == "FAIL"
    assert any("refuses non-success evidence batches" in error for error in result["errors"])
