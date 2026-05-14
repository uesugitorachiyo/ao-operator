from __future__ import annotations

import subprocess

import factory_run


def git(command: list[str], cwd) -> None:
    completed = subprocess.run(
        ["git", *command],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_sync_agent_manifests_preserves_existing_target_manifest(tmp_path, monkeypatch):
    source_root = tmp_path / "factory"
    source = source_root / ".codex" / "agents"
    source.mkdir(parents=True)
    (source / "codex-default.yaml").write_text("factory manifest\n", encoding="utf-8")
    monkeypatch.setattr(factory_run, "ROOT", source_root)

    target = tmp_path / "target"
    destination = target / ".codex" / "agents"
    destination.mkdir(parents=True)
    existing = destination / "codex-default.yaml"
    existing.write_text("target manifest\n", encoding="utf-8")

    factory_run.sync_agent_manifests_to(target)

    assert existing.read_text(encoding="utf-8") == "target manifest\n"


def test_sync_agent_manifests_copies_missing_manifest(tmp_path, monkeypatch):
    source_root = tmp_path / "factory"
    source = source_root / ".codex" / "agents"
    source.mkdir(parents=True)
    (source / "extra.yaml").write_text("factory extra\n", encoding="utf-8")
    monkeypatch.setattr(factory_run, "ROOT", source_root)

    target = tmp_path / "target"
    (target / ".codex" / "agents").mkdir(parents=True)

    factory_run.sync_agent_manifests_to(target)

    assert (target / ".codex" / "agents" / "extra.yaml").read_text(encoding="utf-8") == "factory extra\n"


def test_sync_generated_artifacts_to_workspace_root_copies_and_ignores_factory_files(tmp_path, monkeypatch):
    factory = tmp_path / "factory"
    factory.mkdir()
    monkeypatch.setattr(factory_run, "ROOT", factory)

    status_dir = factory / "run-artifacts" / "slug"
    prompts_dir = status_dir / "prompts"
    prompts_dir.mkdir(parents=True)
    paths = {
        "spec": factory / "docs" / "specs" / "slug-spec.md",
        "plan": factory / "docs" / "plans" / "slug-plan.md",
        "runspec": status_dir / "slug.runspec.yaml",
        "status": status_dir / "slug-status.md",
        "prompts_dir": prompts_dir,
        "evaluation": factory / "docs" / "evaluations" / "slug-evaluation.md",
        "topology": factory / "examples" / "stress" / "topology.yaml",
    }
    for key, path in paths.items():
        if key == "prompts_dir":
            (path / "planner-intake.md").write_text("prompt\n", encoding="utf-8")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(key + "\n", encoding="utf-8")

    target = tmp_path / "target"
    target.mkdir()
    git(["init", "-q"], target)
    git(["config", "user.email", "test@example.com"], target)
    git(["config", "user.name", "Test User"], target)
    (target / "README.md").write_text("target\n", encoding="utf-8")
    git(["add", "README.md"], target)
    git(["commit", "-q", "-m", "seed"], target)

    factory_run.sync_generated_artifacts_to_workspace_root(paths, target, contract=None)

    assert (target / "docs" / "specs" / "slug-spec.md").read_text(encoding="utf-8") == "spec\n"
    assert (target / "examples" / "stress" / "topology.yaml").read_text(encoding="utf-8") == "topology\n"
    assert (target / "run-artifacts" / "slug" / "prompts" / "planner-intake.md").is_file()
    status = subprocess.run(
        ["git", "-C", str(target), "status", "--short"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    assert status.stdout == ""


def test_sync_generated_artifacts_to_worktrees_copies_only_assigned_prompts(tmp_path, monkeypatch):
    factory = tmp_path / "factory"
    factory.mkdir()
    monkeypatch.setattr(factory_run, "ROOT", factory)

    status_dir = factory / "run-artifacts" / "slug"
    prompts_dir = status_dir / "prompts"
    prompts_dir.mkdir(parents=True)
    paths = {
        "spec": factory / "docs" / "specs" / "slug-spec.md",
        "plan": factory / "docs" / "plans" / "slug-plan.md",
        "status_dir": status_dir,
        "runspec": status_dir / "slug.runspec.yaml",
        "status": status_dir / "slug-status.md",
        "events": status_dir / "slug-ao-events.md",
        "prompts_dir": prompts_dir,
        "topology": factory / "examples" / "stress" / "topology.yaml",
    }
    for key, path in paths.items():
        if key == "prompts_dir":
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(key + "\n", encoding="utf-8")
    for prompt_name in ["slice-a-factory", "slice-a-reviewer", "slice-b-factory"]:
        (prompts_dir / f"{prompt_name}.md").write_text(prompt_name + "\n", encoding="utf-8")

    workspace_root = tmp_path / "workspace-root"
    workspace_root.mkdir()
    worktree = tmp_path / "worktree-a"
    worktree.mkdir()
    stale_status = worktree / "run-artifacts" / "slug"
    (stale_status / "roles").mkdir(parents=True)
    (stale_status / "patches").mkdir(parents=True)
    (stale_status / "roles" / "slice-a-factory.md").write_text("Result: BLOCKED\n", encoding="utf-8")
    (stale_status / "patches" / "slice-a-factory.patch").write_text("stale\n", encoding="utf-8")
    (stale_status / "slug-ao-events.md").write_text("stale events\n", encoding="utf-8")
    tasks = [
        {"id": "slice-a-factory", "workspace": str(worktree)},
        {"id": "slice-a-reviewer", "workspace": str(worktree)},
        {"id": "slice-b-factory", "workspace": str(workspace_root)},
    ]

    factory_run.sync_generated_artifacts_to_worktrees(paths, tasks, contract=None, workspace_root=workspace_root)

    copied_prompts = sorted(
        path.name for path in (worktree / "run-artifacts" / "slug" / "prompts").glob("*.md")
    )
    assert copied_prompts == ["slice-a-factory.md", "slice-a-reviewer.md"]
    assert (worktree / "docs" / "specs" / "slug-spec.md").read_text(encoding="utf-8") == "spec\n"
    assert (worktree / "examples" / "stress" / "topology.yaml").read_text(encoding="utf-8") == "topology\n"
    assert not (stale_status / "roles").exists()
    assert not (stale_status / "patches").exists()
    assert not (stale_status / "slug-ao-events.md").exists()
    assert not (workspace_root / "run-artifacts" / "slug" / "prompts").exists()


def test_sync_generated_artifacts_to_worktrees_skips_same_file_generated_inputs(tmp_path, monkeypatch):
    factory = tmp_path / "factory"
    factory.mkdir()
    monkeypatch.setattr(factory_run, "ROOT", factory)

    status_dir = factory / "run-artifacts" / "slug"
    prompts_dir = status_dir / "prompts"
    prompts_dir.mkdir(parents=True)
    paths = {
        "spec": factory / "docs" / "specs" / "slug-spec.md",
        "plan": factory / "docs" / "plans" / "slug-plan.md",
        "runspec": status_dir / "slug.runspec.yaml",
        "status": status_dir / "slug-status.md",
        "prompts_dir": prompts_dir,
        "topology": factory / "examples" / "stress" / "topology.yaml",
    }
    contract = factory / "examples" / "stress" / "contract.json"
    for path in [*paths.values(), contract]:
        if path == prompts_dir:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("content\n", encoding="utf-8")
    (prompts_dir / "factory-a.md").write_text("factory-a\n", encoding="utf-8")

    workspace_root = tmp_path / "workspace-root"
    workspace_root.mkdir()
    tasks = [{"id": "factory-a", "workspace": str(factory)}]

    factory_run.sync_generated_artifacts_to_worktrees(paths, tasks, contract=contract, workspace_root=workspace_root)

    assert contract.read_text(encoding="utf-8") == "content\n"


def test_sync_scoped_reads_to_workspace_root_copies_declared_factory_context(tmp_path, monkeypatch):
    factory = tmp_path / "factory"
    factory.mkdir()
    monkeypatch.setattr(factory_run, "ROOT", factory)
    (factory / "docs" / "sdd").mkdir(parents=True)
    (factory / "docs" / "sdd" / "README.md").write_text("sdd\n", encoding="utf-8")
    (factory / "ao" / "policy").mkdir(parents=True)
    (factory / "ao" / "policy" / "local-dev.yaml").write_text("policy\n", encoding="utf-8")

    target = tmp_path / "target"
    target.mkdir()
    git(["init", "-q"], target)
    git(["config", "user.email", "test@example.com"], target)
    git(["config", "user.name", "Test User"], target)
    (target / "README.md").write_text("target\n", encoding="utf-8")
    git(["add", "README.md"], target)
    git(["commit", "-q", "-m", "seed"], target)
    intake = factory_run.Intake(
        slug="slug",
        brief_path=factory / "brief.md",
        brief="brief",
        classification="COMPLEX",
        shape="refactor",
        blocked=False,
        blocker="",
        acceptance=[],
        scoped_reads=["task brief", "docs/sdd/", "ao/policy/local-dev.yaml", "missing/"],
        scoped_writes=[],
    )

    factory_run.sync_scoped_reads_to_workspace_root(intake, target)

    assert (target / "docs" / "sdd" / "README.md").read_text(encoding="utf-8") == "sdd\n"
    assert (target / "ao" / "policy" / "local-dev.yaml").read_text(encoding="utf-8") == "policy\n"
    status = subprocess.run(
        ["git", "-C", str(target), "status", "--short"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    assert status.stdout == ""


def test_sync_task_scoped_reads_to_worktrees_copies_external_ao_runtime_context(tmp_path, monkeypatch):
    factory = tmp_path / "factory"
    factory.mkdir()
    monkeypatch.setattr(factory_run, "ROOT", factory)

    ao_runtime = tmp_path / "ao-runtime"
    source = ao_runtime / "crates" / "ao-node" / "src" / "registry.rs"
    source.parent.mkdir(parents=True)
    source.write_text("pub struct Registry;\n", encoding="utf-8")
    monkeypatch.setenv("FACTORY_V3_AO_RUNTIME_PATH", str(ao_runtime))

    workspace_root = tmp_path / "workspace-root"
    workspace_root.mkdir()
    worktree = tmp_path / "worktree-a"
    worktree.mkdir()
    git(["init", "-q"], worktree)
    git(["config", "user.email", "test@example.com"], worktree)
    git(["config", "user.name", "Test User"], worktree)
    (worktree / "README.md").write_text("target\n", encoding="utf-8")
    git(["add", "README.md"], worktree)
    git(["commit", "-q", "-m", "seed"], worktree)

    tasks = [
        {
            "id": "identity-factory",
            "workspace": str(worktree),
            "reads": ["crates/ao-node/src/registry.rs", "task brief", "missing.rs"],
        },
        {
            "id": "heartbeat-factory",
            "workspace": str(workspace_root),
            "reads": ["crates/ao-node/src/registry.rs"],
        },
    ]

    factory_run.sync_task_scoped_reads_to_worktrees(tasks, workspace_root, "slug")

    copied = worktree / "crates" / "ao-node" / "src" / "registry.rs"
    assert copied.read_text(encoding="utf-8") == "pub struct Registry;\n"
    assert not (workspace_root / "crates" / "ao-node" / "src" / "registry.rs").exists()
    status = subprocess.run(
        ["git", "-C", str(worktree), "status", "--short"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    assert status.stdout == ""


def test_sync_factory_helper_scripts_to_workspace_root_copies_and_ignores_helpers(tmp_path, monkeypatch):
    factory = tmp_path / "factory"
    factory.mkdir()
    monkeypatch.setattr(factory_run, "ROOT", factory)
    (factory / "scripts").mkdir()
    (factory / "scripts" / "validate_intake.py").write_text("validate\n", encoding="utf-8")
    (factory / "scripts" / "verify_closure.py").write_text("verify\n", encoding="utf-8")

    target = tmp_path / "target"
    target.mkdir()
    git(["init", "-q"], target)
    git(["config", "user.email", "test@example.com"], target)
    git(["config", "user.name", "Test User"], target)
    (target / "README.md").write_text("target\n", encoding="utf-8")
    git(["add", "README.md"], target)
    git(["commit", "-q", "-m", "seed"], target)

    factory_run.sync_factory_helper_scripts_to_workspace_root(target)

    assert (target / "scripts" / "validate_intake.py").read_text(encoding="utf-8") == "validate\n"
    assert (target / "scripts" / "verify_closure.py").read_text(encoding="utf-8") == "verify\n"
    status = subprocess.run(
        ["git", "-C", str(target), "status", "--short"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    assert status.stdout == ""


def test_sync_generated_artifacts_to_worktrees_copies_only_assigned_prompts(tmp_path, monkeypatch):
    factory = tmp_path / "factory"
    factory.mkdir()
    monkeypatch.setattr(factory_run, "ROOT", factory)

    status_dir = factory / "run-artifacts" / "slug"
    prompts_dir = status_dir / "prompts"
    prompts_dir.mkdir(parents=True)
    paths = {
        "spec": factory / "docs" / "specs" / "slug-spec.md",
        "plan": factory / "docs" / "plans" / "slug-plan.md",
        "runspec": status_dir / "slug.runspec.yaml",
        "status": status_dir / "slug-status.md",
        "prompts_dir": prompts_dir,
    }
    for key, path in paths.items():
        if key == "prompts_dir":
            for task_id in ("factory-a", "reviewer-a", "factory-b", "reviewer-b", "integrator"):
                (path / f"{task_id}.md").write_text(f"{task_id}\n", encoding="utf-8")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(key + "\n", encoding="utf-8")

    workspace_a = tmp_path / "workspace-a"
    workspace_b = tmp_path / "workspace-b"
    workspace_a.mkdir()
    workspace_b.mkdir()
    tasks = [
        {"id": "factory-a", "workspace": str(workspace_a)},
        {"id": "reviewer-a", "workspace": str(workspace_a)},
        {"id": "factory-b", "workspace": str(workspace_b)},
        {"id": "reviewer-b", "workspace": str(workspace_b)},
        {"id": "integrator", "workspace": str(factory)},
    ]

    factory_run.sync_generated_artifacts_to_worktrees(paths, tasks, contract=None, workspace_root=factory)

    synced_a = sorted(path.name for path in (workspace_a / "run-artifacts/slug/prompts").glob("*.md"))
    synced_b = sorted(path.name for path in (workspace_b / "run-artifacts/slug/prompts").glob("*.md"))
    assert synced_a == ["factory-a.md", "reviewer-a.md"]
    assert synced_b == ["factory-b.md", "reviewer-b.md"]
