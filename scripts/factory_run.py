#!/usr/bin/env python3
"""Run the AO Operator local AO-backed pipeline."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil
from pathlib import Path

import auto_partition
import factory_ao_adapter
import factory_event_normalizer
import factory_profiles
import factory_v3_config
import gate_b
import gate_r
import obligation_ledger

ROOT = Path(__file__).resolve().parents[1]
AO_RUNTIME_DEFAULT = (ROOT / ".." / "ao-runtime").resolve()
VALID_PROVIDERS = {"claude", "codex", "antigravity"}
FORBIDDEN_ENV = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")
MAX_INJECTED_ARTIFACT_CHARS = 12000
WORKTREE_ROOT_ENV = "FACTORY_V3_WORKTREE_ROOT"
STANDALONE_PROFILE_HANDOFFS = {
    "financial-services:earnings-note": {
        "repo": "../financial-services-profile",
        "workflow": "earnings-note",
        "command": "fsp run earnings-note --engine ao",
        "approval": (
            "add --approval-ticket-id and --approval-db for non-demo approval evidence"
        ),
        "status": "run-artifacts/financial-services-profile-v0.3-standalone.md",
    },
    "financial-services:kyc-document-triage": {
        "repo": "../financial-services-profile",
        "workflow": "kyc-document-triage",
        "command": "fsp run kyc-document-triage --engine ao",
        "approval": (
            "add --approval-ticket-id and --approval-db for non-demo approval evidence"
        ),
        "status": "run-artifacts/financial-services-profile-v0.3-standalone.md",
    },
}


def _resolve_worktree_root() -> Path:
    override = os.environ.get(WORKTREE_ROOT_ENV)
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "ao-operator-worktrees"


WORKTREE_ROOT = _resolve_worktree_root()
WORKTREE_LEASE_SCHEMA = "ao-operator/worktree-lease/v1"
WORKTREE_LEASE_DIRNAME = ".leases"
PROFILES_DIR = factory_profiles.PROFILES_DIR
PROFILE_SCHEMA_ID = factory_profiles.PROFILE_SCHEMA_ID
PROFILE_VERSION = factory_profiles.PROFILE_VERSION
ProfileError = factory_profiles.ProfileError
BASELINE_TASKS = factory_profiles.BASELINE_TASKS
DEFAULT_MAX_LIVE_TASKS = 50
MAX_LIVE_TASKS_ENV = "FACTORY_V3_MAX_LIVE_TASKS"
ALLOW_LARGE_LIVE_RUN_ENV = "FACTORY_V3_ALLOW_LARGE_LIVE_RUN"
_CLAUDE_MEM_BLOCK_RE = re.compile(
    r"\n*<claude-mem-context>.*?</claude-mem-context>\n*",
    re.DOTALL,
)


def _validate_profile(name: str, raw: object) -> dict[str, object]:
    return factory_profiles.validate_profile(name, raw)


def _load_profile(name: str, repo_root: Path | None = None) -> dict[str, object]:
    return factory_profiles.load_profile(name, repo_root)


def _list_profiles(repo_root: Path | None = None) -> list[dict[str, str]]:
    return factory_profiles.list_profiles(repo_root)


def _standalone_profile_handoff(profile_name: str) -> dict[str, str] | None:
    return STANDALONE_PROFILE_HANDOFFS.get(profile_name)


def _standalone_profile_handoff_message(profile_name: str) -> str:
    handoff = _standalone_profile_handoff(profile_name)
    if handoff is None:
        return ""
    return "\n".join(
        [
            (
                f"factory_run.py: profile {profile_name!r} runs in the standalone "
                "Financial Services Profile repo."
            ),
            "AO Operator keeps profiles/financial-services/* as inspectable role-chain contracts.",
            f"Use: cd {handoff['repo']} && {handoff['command']}",
            f"Approval evidence: {handoff['approval']}",
            f"Status: {handoff['status']}",
        ]
    )


_ACTIVE_PROFILE: dict[str, object] | None = None


def _set_active_profile(profile: dict[str, object] | None) -> None:
    """Set the module-level active profile that legacy callers consult.

    main() calls this once with the loaded profile when --profile is not
    'default'. When no profile is active, callers fall through to legacy
    behavior, preserving byte-for-byte parity with v0.1.0.
    """
    global _ACTIVE_PROFILE
    _ACTIVE_PROFILE = profile


def _active_profile() -> dict[str, object] | None:
    return _ACTIVE_PROFILE


_ACTIVE_REMOTE: bool = False


def _set_active_remote(remote: bool) -> None:
    """Set the module-level --remote flag (v0.2 D2).

    main() calls this once after argparse. When True, runspec_body emits
    per-task `hostTags` lines for any task whose role declared `host_tag`.
    When False (default), the RunSpec is byte-for-byte identical to v0.1.1
    output for any legacy profile, preserving the parity guarantee.
    """
    global _ACTIVE_REMOTE
    _ACTIVE_REMOTE = bool(remote)


def _active_remote() -> bool:
    return _ACTIVE_REMOTE


def _tasks_from_profile(profile: dict[str, object]) -> list[dict[str, object]]:
    return factory_profiles.tasks_from_profile(profile)


def _render_policy_yaml(profile: dict[str, object], slug: str) -> str:
    return factory_profiles.render_policy_yaml(profile, slug)


def _profile_has_policy_posture(profile: dict[str, object] | None) -> bool:
    return factory_profiles.profile_has_policy_posture(profile)


def expand_slice_topology(
    baseline: list[dict[str, object]],
    num_slices: int,
    slice_specs: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    """Expand `implementer-slice` / `reviewer-slice` into N pairs.

    For num_slices == 1: returns `baseline` unchanged (today's behavior).
    For num_slices >= 2: replaces the single implementer-slice with
    implementer-slice-1..N, the single reviewer-slice with
    reviewer-slice-1..N, and rewires the integrator's deps to depend on all
    reviewer-slice-* tasks.

    Each reviewer-slice-i depends only on its paired implementer-slice-i
    (preserves slice independence — a slice's reviewer never blocks on
    another slice's implementer).

    When `slice_specs` comes from auto_partition.partition(), each expanded
    implementer receives only its assigned writes. This is the scoped-write
    contract that keeps parallel slices from drifting across ownership
    boundaries.
    """
    if num_slices <= 1:
        return baseline

    writes_by_slice: dict[int, list[str]] = {}
    for spec in slice_specs or []:
        try:
            slice_index = int(spec.get("slice_id", 0))
        except (TypeError, ValueError):
            continue
        writes = spec.get("writes", [])
        if isinstance(writes, list):
            writes_by_slice[slice_index] = [str(item) for item in writes]

    expanded: list[dict[str, object]] = []
    reviewer_ids: list[str] = []
    for task in baseline:
        task_id = str(task["id"])
        if task_id == "implementer-slice":
            for i in range(1, num_slices + 1):
                expanded_task = {**task, "id": f"implementer-slice-{i}"}
                if i in writes_by_slice:
                    expanded_task["writes"] = writes_by_slice[i]
                expanded.append(expanded_task)
        elif task_id == "reviewer-slice":
            for i in range(1, num_slices + 1):
                slice_id = f"reviewer-slice-{i}"
                reviewer_ids.append(slice_id)
                expanded.append({
                    **task,
                    "id": slice_id,
                    "deps": [f"implementer-slice-{i}"],
                })
        elif task_id == "integrator":
            expanded.append({**task, "deps": reviewer_ids})
        else:
            expanded.append(task)
    return expanded


TASKS = BASELINE_TASKS

MUTATOR_PROVIDER_KEYS = {str(task["id"]): str(task["provider_key"]) for task in BASELINE_TASKS}
PROVIDER_KEYS = {
    **MUTATOR_PROVIDER_KEYS,
    "spec-forge-contract": "FACTORY_V3_SPEC_FORGE_PROVIDER",
    "ralph-loop": "FACTORY_V3_RALPH_LOOP_PROVIDER",
}


def provider_key_for_task(task_id: str) -> str:
    if task_id in PROVIDER_KEYS:
        return PROVIDER_KEYS[task_id]
    if task_id.endswith("-factory"):
        return "FACTORY_V3_IMPLEMENTER_PROVIDER"
    if task_id.endswith("-reviewer"):
        return "FACTORY_V3_SLICE_REVIEWER_PROVIDER"
    return "FACTORY_V3_DEFAULT_PROVIDER"


def exact_provider_key_for_task(task_id: str) -> str:
    return "FACTORY_V3_" + re.sub(r"[^A-Za-z0-9]+", "_", task_id).upper().strip("_") + "_PROVIDER"


def provider_keys_for_task(task_id: str) -> list[str]:
    keys = [exact_provider_key_for_task(task_id), provider_key_for_task(task_id)]
    return list(dict.fromkeys(keys))


def title_role(task_id: str) -> str:
    return task_id.replace("-", " ").title()


def _is_slice_implementer(task_id: str) -> bool:
    return task_id == "implementer-slice" or task_id.startswith("implementer-slice-")


def _is_slice_reviewer(task_id: str) -> bool:
    return task_id == "reviewer-slice" or task_id.startswith("reviewer-slice-")


def _split_topology_for_n_ge_2(
    tasks: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Split an expanded multi-slice topology into chain-1 / chain-2 lists.

    Chain 1 contains every task EXCEPT integrator and evaluator-closer.
    Chain 2 contains integrator (with deps=[] for AO ordering, and a
    `chain1_handoffs` field listing every reviewer-slice-* task ID for
    prompt-rendering context injection) and evaluator-closer (with
    deps=["integrator"] for intra-chain-2 ordering).

    The split is purely structural; chain 2 will be dispatched in a
    second AO call after factory_run.py materializes the integrator
    workspace via git-apply (SDD 09).

    Defensive: handles N=1 input gracefully even though main() only
    invokes this helper when num_slices >= 2.
    """
    chain1: list[dict[str, object]] = []
    chain2_integrator: dict[str, object] | None = None
    chain2_evaluator: dict[str, object] | None = None
    reviewer_slice_ids: list[str] = []
    chain1_task_ids: list[str] = []
    for task in tasks:
        tid = str(task["id"])
        if tid == "integrator":
            chain2_integrator = {**task}
        elif tid == "evaluator-closer":
            chain2_evaluator = {**task}
        else:
            chain1.append(task)
            chain1_task_ids.append(tid)
            if _is_slice_reviewer(tid):
                reviewer_slice_ids.append(tid)
    if chain2_integrator is None:
        raise ValueError("integrator missing from baseline topology")
    if chain2_evaluator is None:
        raise ValueError("evaluator-closer missing from baseline topology")
    chain2_integrator["deps"] = []
    chain2_integrator["chain1_handoffs"] = reviewer_slice_ids
    chain2_evaluator["deps"] = ["integrator"]
    # evaluator-closer needs visibility into every chain-1 task artifact to
    # render a deterministic ACCEPTED/REJECTED verdict — it must see all
    # implementer-slice-* DONE evidence, all reviewer-slice-* artifacts, and
    # planner-intake / plan-hardener / factory-manager outputs. With only
    # deps=["integrator"], the evaluator's prompt loses chain-1 context.
    chain2_evaluator["chain1_handoffs"] = chain1_task_ids
    return chain1, [chain2_integrator, chain2_evaluator]


def is_mutator_task(task_id: str, profile: dict[str, object] | None = None) -> bool:
    profile = profile if profile is not None else _active_profile()
    if profile is not None:
        role = profile.get("roles_by_id", {}).get(task_id)
        if isinstance(role, dict) and isinstance(role.get("is_mutator"), bool):
            return bool(role["is_mutator"])
    return _is_slice_implementer(task_id) or (task_id.endswith("-factory") and task_id != "factory-manager")


def default_reads_writes(task_id: str, slug: str, contract: dict[str, object] | None = None, profile: dict[str, object] | None = None) -> tuple[list[str], list[str]]:
    profile = profile if profile is not None else _active_profile()
    if profile is not None:
        role = profile.get("roles_by_id", {}).get(task_id)
        if isinstance(role, dict):
            return list(role.get("reads", [])), list(role.get("writes", []))
    for task in BASELINE_TASKS:
        if task["id"] == task_id:
            return list(task["reads"]), list(task["writes"])
    if task_id == "spec-forge-contract":
        return ["task brief", "docs/sdd/"], ["examples/outperform-ai-teams-fanout/spec-forge.contract.json"]
    if task_id == "ralph-loop":
        return ["docs/specs/<slug>-spec.md", "spec-forge.contract.json"], [f"run-artifacts/{slug}/roles/ralph-loop.md"]
    if task_id.endswith("-factory"):
        for item in (contract or {}).get("slices", []):
            if isinstance(item, dict) and item.get("id") == task_id:
                reads = [str(v) for v in item.get("reads", [])]
                writes = [str(v) for v in item.get("writes", [])]
                return reads or ["spec-forge.contract.json"], writes or ["scoped branch artifacts"]
        return ["spec-forge.contract.json", "docs/plans/<slug>-plan.md"], ["scoped branch artifacts"]
    if task_id.endswith("-reviewer"):
        factory_id = task_id.removesuffix("-reviewer") + "-factory"
        reads = [f"run-artifacts/{slug}/roles/{factory_id}.md", "spec-forge.contract.json"]
        for item in (contract or {}).get("slices", []):
            if isinstance(item, dict) and item.get("id") == factory_id:
                reads.extend(str(v) for v in item.get("writes", []))
                break
        return list(dict.fromkeys(reads)), [f"run-artifacts/{slug}/roles/{task_id}.md"]
    return ["docs/specs/<slug>-spec.md", "docs/plans/<slug>-plan.md"], [f"run-artifacts/{slug}/roles/{task_id}.md"]


def skills_for_task(task_id: str, profile: dict[str, object] | None = None) -> list[str]:
    profile = profile if profile is not None else _active_profile()
    if profile is not None:
        role = profile.get("roles_by_id", {}).get(task_id)
        if isinstance(role, dict):
            return list(
                dict.fromkeys(
                    ["skills/factory-intake/SKILL.md", *list(role.get("skills", []))]
                )
            )
    skills = ["skills/factory-intake/SKILL.md"]
    if task_id == "plan-hardener":
        skills.append("skills/plan-hardener/SKILL.md")
    if task_id in {"spec-forge-contract", "ralph-loop", "plan-hardener", "factory-manager"} or task_id.endswith("-factory"):
        skills.append("skills/spec-forge-contracting/SKILL.md")
    if task_id.endswith("-factory") or task_id == "factory-manager":
        skills.append("skills/context-offload/SKILL.md")
    if task_id.endswith("-reviewer") or task_id in {"integrator", "evaluator-closer", "ralph-loop"}:
        skills.append("skills/closure-verification/SKILL.md")
    if task_id == "evaluator-closer":
        skills.append("skills/mission-monitor-ops/SKILL.md")
    return list(dict.fromkeys(skills))


def inline_skills(task_id: str) -> str:
    """Render the role's relevant skills as inlined content, not just paths.

    Agents under bounded provider configs (e.g., Claude with --tools "")
    cannot Read skill files at runtime. Inlining puts the skill body in
    the prompt directly so both providers benefit equally from the skill
    investment.
    """
    parts: list[str] = []
    for skill_path in skills_for_task(task_id):
        full = ROOT / skill_path
        if not full.is_file():
            parts.append(f"### {skill_path} (file not found)")
            continue
        skill_name = Path(skill_path).parent.name
        content = full.read_text(encoding="utf-8").strip()
        parts.append(f"### {skill_name}\n\nSource: `{skill_path}`\n\n{content}")
    return "\n\n".join(parts) if parts else "_No relevant skills declared for this role._"


@dataclass(frozen=True)
class Intake:
    slug: str
    brief_path: Path
    brief: str
    classification: str
    shape: str
    blocked: bool
    blocker: str
    acceptance: list[str]
    scoped_reads: list[str]
    scoped_writes: list[str]


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def reject_forbidden_env() -> str | None:
    present = [key for key in FORBIDDEN_ENV if os.environ.get(key)]
    if present:
        return "Forbidden provider API-key env var present: " + ", ".join(present)
    return None


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "ao-operator-task"


def classify(brief: str) -> tuple[str, str]:
    text = brief.lower()
    explicit_shapes = [
        ("greenfield", ["shape: greenfield", "shape it as greenfield", "shape as greenfield"]),
        ("bug-fix", ["shape: bug-fix", "shape it as bug-fix", "shape as bug-fix"]),
        ("refactor", ["shape: refactor", "shape it as refactor", "shape as refactor"]),
    ]
    shape = ""
    for candidate, needles in explicit_shapes:
        if any(needle in text for needle in needles):
            shape = candidate
            break

    if shape:
        pass
    elif any(word in text for word in ["bug", "failing", "regression", "error", "broken", "fix"]):
        shape = "bug-fix"
    elif any(word in text for word in ["refactor", "reorganize", "preserve behavior", "cleanup", "migrate"]):
        shape = "refactor"
    else:
        shape = "greenfield"

    complex_terms = [
        "complex",
        "multiple",
        "frontend",
        "backend",
        "database",
        "factory",
        "orchestration",
        "users",
        "projects",
        "tasks",
        "comments",
    ]
    if sum(1 for term in complex_terms if term in text) >= 3 or "complex" in text:
        classification = "COMPLEX"
    elif len([line for line in brief.splitlines() if line.strip().startswith("-")]) >= 3:
        classification = "MODERATE"
    else:
        classification = "TRIVIAL"
    return classification, shape


def extract_scoped_writes(brief: str) -> list[str]:
    patterns = [
        re.compile(r"^[ \t-]*(?:[Oo]ne|[Tt]wo|[Tt]hree)? ?file edits?:?\s*([^\s]+)"),
        re.compile(r"^[ \t-]*[Nn]ew file:\s*([^\s]+)"),
        re.compile(r"^[ \t-]*[Ee]dit:?\s*([^\s]+)"),
    ]
    extensions = (".py", ".md", ".sh", ".toml", ".yaml", ".yml", ".json")
    scoped_writes: list[str] = []
    for line in brief.splitlines():
        for pattern in patterns:
            match = pattern.match(line)
            if not match:
                continue
            path = match.group(1).strip("`'\"")
            path = path.rstrip(".,;:)]}").strip("`'\"")
            if "/" not in path and not path.endswith(extensions):
                continue
            scoped_writes.append(path)
            break
    return list(dict.fromkeys(scoped_writes))


def build_acceptance(shape: str) -> list[str]:
    base = [
        "AO Operator generates a complete spec, hardened plan, status log, materialized prompts, RunSpec, and evaluation artifact.",
        "Provider selection resolves only to codex, claude, or antigravity and never requires provider API keys.",
        "AO execution evidence is captured durably when live mode is used.",
    ]
    if shape == "greenfield":
        base.append("Greenfield scope includes explicit acceptance criteria and scoped write boundaries before dispatch.")
    elif shape == "bug-fix":
        base.append("Bug-fix closure includes failing reproducer evidence and red-to-green verification.")
    else:
        base.append("Refactor closure includes pinning-suite evidence and behavior-preservation verification.")
    return base


def shape_gate(shape: str, brief: str) -> tuple[bool, str]:
    text = brief.lower()
    if shape == "greenfield":
        has_scope = any(word in text for word in ["build", "create", "produce", "use factory", "scope"])
        if has_scope:
            return False, "greenfield gate satisfied: outcome, scope, acceptance, and scoped writes generated"
        return True, "greenfield gate missing clear outcome/scope language"
    if shape == "bug-fix":
        has_reproducer = any(
            phrase in text
            for phrase in [
                "reproducer evidence:",
                "failing reproducer evidence:",
                "failing test:",
                "red-to-green evidence:",
            ]
        )
        if has_reproducer:
            return False, "bug-fix gate satisfied: failing reproducer evidence declared"
        return True, 'bug-fix gate blocked: failing reproducer evidence is required before mutator dispatch. Add a "Failing reproducer evidence:" or "Failing test:" or "Red-to-green evidence:" section to the brief.'
    has_pinning = any(
        phrase in text
        for phrase in [
            "pinning suite:",
            "pinned test:",
            "preservation test:",
            "golden test:",
        ]
    )
    if has_pinning:
        return False, "refactor gate satisfied: pinning-suite evidence declared"
    return True, 'refactor gate blocked: pinning-suite evidence is required before mutator dispatch. Add a "Pinning suite:" or "Pinned test:" or "Preservation test:" or "Golden test:" section to the brief.'


def provider_for(env: dict[str, str], key: str, explicit_default: str | None = None) -> str:
    default = explicit_default or env.get("FACTORY_V3_DEFAULT_PROVIDER") or "codex"
    value = env.get(key, default)
    if value not in VALID_PROVIDERS:
        raise ValueError(f"{key} resolved to unsupported provider {value!r}")
    return value


def load_provider_map(env: dict[str, str] | None = None) -> dict[str, str]:
    """Return {role_id: provider_name} for the 7 ao-operator mutator roles.

    Falls back to FACTORY_V3_DEFAULT_PROVIDER (then 'codex') when a per-role
    env var is unset. `env` defaults to os.environ when None.
    """
    source = os.environ if env is None else env
    return {role_id: provider_for(source, key) for role_id, key in MUTATOR_PROVIDER_KEYS.items()}


def provider_for_task(env: dict[str, str], task: dict[str, object]) -> str:
    task_id = str(task["id"])
    explicit_default = str(task.get("provider") or "") or None
    default = env.get("FACTORY_V3_DEFAULT_PROVIDER") or explicit_default or "codex"
    for key in provider_keys_for_task(task_id):
        if key in env:
            value = env[key]
            if value not in VALID_PROVIDERS:
                raise ValueError(f"{key} resolved to unsupported provider {value!r}")
            return value
    if default not in VALID_PROVIDERS:
        raise ValueError(f"{task_id} resolved to unsupported provider {default!r}")
    return default


def provider_map(env: dict[str, str], tasks: list[dict[str, object]]) -> dict[str, str]:
    mutator_providers = load_provider_map(env)
    return {
        str(task["id"]): mutator_providers.get(str(task["id"])) or provider_for_task(env, task)
        for task in tasks
    }


def load_contract(path: Path | None) -> dict[str, object] | None:
    if not path:
        return None
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        raise ValueError(f"missing contract file {path}")
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"contract file {path} must contain a JSON object")
    return data


def parse_inline_list(value: str) -> list[str]:
    return re.findall(r'"([^"]+)"', value)


def parse_spec_value(raw: str) -> object:
    raw = raw.strip()
    if raw in {"true", "false"}:
        return raw == "true"
    if raw.startswith("[") and raw.endswith("]"):
        return parse_inline_list(raw)
    return raw.strip('"')


def parse_topology(path: Path, slug: str, contract: dict[str, object] | None) -> list[dict[str, object]]:
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        raise ValueError(f"missing topology file {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [idx for idx, line in enumerate(lines) if re.match(r"\s{4}- id:\s*", line)]
    tasks: list[dict[str, object]] = []
    for pos, start in enumerate(starts):
        end = starts[pos + 1] if pos + 1 < len(starts) else len(lines)
        block = lines[start:end]
        task_id = block[0].split(":", 1)[1].strip().strip('"')
        deps: list[str] = []
        spec: dict[str, object] = {}
        dep_idx = next((i for i, line in enumerate(block) if re.match(r"\s+deps:\s*", line)), None)
        spec_idx = next((i for i, line in enumerate(block) if re.match(r"\s+spec:\s*$", line)), len(block))
        if dep_idx is not None:
            dep_line = block[dep_idx]
            after = dep_line.split(":", 1)[1].strip()
            if after.startswith("["):
                deps = parse_inline_list(after)
            else:
                for line in block[dep_idx + 1 : spec_idx]:
                    match = re.match(r"\s+-\s+(.+?)\s*$", line)
                    if match:
                        deps.append(match.group(1).strip().strip('"'))
        for line in block[spec_idx + 1 :]:
            match = re.match(r"\s{8}([A-Za-z][A-Za-z0-9_]*):\s*(.+?)\s*$", line)
            if match:
                spec[match.group(1)] = parse_spec_value(match.group(2))
        reads, writes = default_reads_writes(task_id, slug, contract)
        if task_id == "spec-forge-contract" and spec.get("contractFile"):
            writes = [str(spec["contractFile"])]
        task = {
            "id": task_id,
            "role": title_role(task_id),
            "provider_key": provider_key_for_task(task_id),
            "provider": spec.get("provider"),
            "deps": deps,
            "reads": reads,
            "writes": writes,
            "promptFile": f"run-artifacts/{slug}/prompts/{task_id}.md",
            "extra_spec": {
                key: value
                for key, value in spec.items()
                if key
                not in {
                    "provider",
                    "agent",
                    "promptFile",
                    "workspace",
                    "policyProfile",
                    "deterministic",
                    "replay_command",
                    "replay_outputs",
                }
            },
        }
        for field in ("deterministic", "replay_command", "replay_outputs"):
            if field in spec:
                task[field] = spec[field]
        tasks.append(task)
    if not tasks:
        raise ValueError(f"topology file {path} has no tasks")
    return tasks


def rel(path: Path) -> str:
    # POSIX separators so paths emitted into .git/info/exclude, JSON
    # artifacts and operator-visible reports parse identically on
    # Linux/macOS/Windows. Without this, Windows backslashes get
    # interpreted as escape sequences by gitignore and break consumers.
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return Path(path).as_posix()


def display_path(path: Path) -> str:
    public_path = rel(path) if path.is_absolute() else Path(path).as_posix()
    legacy_status_prefix = "/".join(["docs", "status", ""])
    if public_path.startswith(legacy_status_prefix):
        return "run-artifacts/" + public_path[len(legacy_status_prefix) :]
    return public_path


def normalize_generated_text(body: str) -> str:
    """Keep generated markdown/YAML artifacts friendly to git diff checks."""
    return "\n".join(line.rstrip() for line in body.splitlines()) + "\n"


def write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(normalize_generated_text(body), encoding="utf-8")


def write_json(path: Path, body: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_for_prompt(path: Path, max_chars: int = MAX_INJECTED_ARTIFACT_CHARS) -> str:
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        return f"(missing: {display_path(path)})"
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n[truncated after {max_chars} chars]"


def fenced(path: Path, body: str) -> str:
    return f"### {display_path(path)}\n\n```text\n{body.rstrip()}\n```"


def make_intake(brief_path: Path, slug: str | None) -> Intake:
    brief = brief_path.read_text(encoding="utf-8")
    actual_slug = slugify(slug or brief_path.stem)
    classification, shape = classify(brief)
    blocked, blocker = shape_gate(shape, brief)
    metadata_writes = [
        f"docs/specs/{actual_slug}-spec.md",
        f"docs/plans/{actual_slug}-plan.md",
        f"run-artifacts/{actual_slug}/",
        f"docs/evaluations/{actual_slug}-evaluation.md",
    ]
    return Intake(
        slug=actual_slug,
        brief_path=brief_path,
        brief=brief,
        classification=classification,
        shape=shape,
        blocked=blocked,
        blocker=blocker,
        acceptance=build_acceptance(shape),
        scoped_reads=[rel(brief_path), "docs/sdd/", "agents/", "ao/policy/local-dev.yaml"],
        scoped_writes=list(dict.fromkeys(extract_scoped_writes(brief) + metadata_writes)),
    )


def bullet(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def spec_body(intake: Intake, providers: dict[str, str]) -> str:
    status = "BLOCKED" if intake.blocked else "READY"
    provider_lines = [f"{task_id}: {provider}" for task_id, provider in providers.items()]
    return f"""# {intake.slug} Spec

Slug: {intake.slug}
Classification: {intake.classification}
Shape: {intake.shape}
Status: {status}
Generated: {datetime.now(timezone.utc).isoformat()}

## Intent

{intake.brief.strip()}

## Scope

- Execute AO Operator as a local AO-backed factory workflow.
- Preserve OAuth/subscription CLI provider auth.
- Generate durable artifacts for every handoff and closure decision.

## Non-goals

- No provider API-key configuration.
- No full-conversation transcript handoff.
- No provider substitution during live execution.

## Acceptance Criteria

{bullet(intake.acceptance)}

## Providers

{bullet(provider_lines)}

## Scoped Reads

{bullet(intake.scoped_reads)}

## Scoped Writes

{bullet(intake.scoped_writes)}

## Sensitive Fields

- Environment variables.
- OAuth tokens and auth files.
- Provider CLI session state.

## Trigger Hints

- docs
- provider-runtime
- security
- build

## Negative Constraints

- Do not read secrets.
- Do not emit raw environment dumps.
- Do not include full transcripts in downstream prompts.
- Do not substitute one resolved provider for another during live execution.

## Verification

- `python3 -m py_compile scripts/*.py`
- `python3 scripts/validate_scaffold.py`
- `python3 scripts/factory_doctor.py`
- `python3 scripts/validate_factory.py --slug {intake.slug}`

## Shape Gate

- Shape: {intake.shape}
- Gate: {intake.blocker}
"""


def plan_body(intake: Intake, providers: dict[str, str], tasks: list[dict[str, object]], topology: Path | None, contract: Path | None) -> str:
    blockers = [intake.blocker] if intake.blocked else ["none"]
    dag_lines = [f"{task['id']} depends on {task['deps'] or ['root']}" for task in tasks]
    ownership = [
        f"{task['id']}: reads {', '.join(task['reads'])}; writes {', '.join(task['writes'])}"
        for task in tasks
    ]
    provider_lines = [f"{task_id}: {provider}" for task_id, provider in providers.items()]
    control = [
        "Spec Forge contract gate: " + (rel(contract) if contract else "not configured"),
        "Ralph Loop gate: required before fan-out" if any(task["id"] == "ralph-loop" for task in tasks) else "Ralph Loop gate: not configured",
        "Topology: " + (rel(topology) if topology else "baseline seven-role DAG"),
    ]
    return f"""# {intake.slug} Hardened Plan

Slug: {intake.slug}
Classification: {intake.classification}
Shape: {intake.shape}
Status: {"BLOCKED" if intake.blocked else "READY"}

## Approach

AO Operator runs a scoped AO DAG: intake, plan hardening, factory management,
implementation, review, integration, and evaluator closure. Each role receives
only the current artifact paths and scoped summaries needed for its work.

## Control Gates

{bullet(control)}

## DAG

{bullet(dag_lines)}

## Role Ownership

{bullet(ownership)}

## Provider Map

{bullet(provider_lines)}

## Artifact Handoffs

- Spec: docs/specs/{intake.slug}-spec.md
- Plan: docs/plans/{intake.slug}-plan.md
- Status: run-artifacts/{intake.slug}/{intake.slug}-status.md
- Prompts: run-artifacts/{intake.slug}/prompts/
- AO events: run-artifacts/{intake.slug}/{intake.slug}-ao-events.md
- Role artifacts: run-artifacts/{intake.slug}/roles/
- Evaluation: docs/evaluations/{intake.slug}-evaluation.md

## Verification Gates

- Provider env must resolve to codex, claude, or antigravity.
- Forbidden provider API-key env vars must be absent.
- Shape gate must pass before mutator dispatch.
- AO completion must be followed by evaluator acceptance.

## Blockers

{bullet(blockers)}

## Recovery

- If provider validation fails, fix `.env` and rerun.
- If a shape gate blocks, update the brief with required evidence and rerun.
- If AO fails, inspect the event summary and rerun with the same slug.
"""


def artifact_injections(intake: Intake, task: dict[str, object], contract_path: Path | None) -> list[str]:
    task_id = str(task["id"])
    spec_path = ROOT / "docs" / "specs" / f"{intake.slug}-spec.md"
    plan_path = ROOT / "docs" / "plans" / f"{intake.slug}-plan.md"
    status_path = ROOT / "run-artifacts" / intake.slug / f"{intake.slug}-status.md"
    events_path = ROOT / "run-artifacts" / intake.slug / f"{intake.slug}-ao-events.md"
    role_dir = ROOT / "run-artifacts" / intake.slug / "roles"
    patch_dir = ROOT / "run-artifacts" / intake.slug / "patches"

    include: list[Path] = []
    if task_id != "planner-intake":
        include.append(spec_path)
    if task_id not in {"planner-intake", "plan-hardener", "spec-forge-contract", "ralph-loop"}:
        include.append(plan_path)
    if contract_path:
        include.append(contract_path if contract_path.is_absolute() else ROOT / contract_path)
    if task_id in {"integrator", "evaluator-closer"}:
        include.append(status_path)
    if task_id == "evaluator-closer" and events_path.is_file():
        include.append(events_path)

    snippets = [fenced(path, read_for_prompt(path)) for path in include]
    if task_id == "evaluator-closer" and not events_path.is_file():
        snippets.append(
            "### Final AO Event Summary\n\n"
            f"- Final AO event artifact path: `{display_path(events_path)}`.\n"
            "- This file is written by AO Operator after AO completes, so it is not available inside the evaluator provider turn.\n"
            "- Do not return BLOCKED solely because the final AO event artifact is absent during this turn."
        )
    if task_id == "evaluator-closer":
        snippets.append(
            "### Runtime Timing Evidence\n\n"
            "- Wallclock and baseline-comparison evidence (e.g. 'wallclock <= 1/3 of N=1 baseline') is measured by AO Operator outside the provider turn and appended to the evaluation artifact post-AO.\n"
            "- Do not return BLOCKED solely because in-turn timing or baseline comparison evidence is absent; treat it as a AO Operator post-AO responsibility.\n"
            "- If every other acceptance criterion is satisfied (marker files exist, all upstream STATUS blocks DONE, deterministic verification commands pass), return DONE."
        )
    deps = [str(dep) for dep in task["deps"]]
    chain1_handoffs = [str(h) for h in task.get("chain1_handoffs", [])]
    # chain1_handoffs lets a chain-2 task (currently: integrator) receive
    # chain-1 reviewer-slice role artifacts despite having empty deps.
    # dict.fromkeys preserves insertion order while deduping, so deps stay
    # first and any chain1_handoffs entry already in deps is dropped — a
    # defense against a future custom topology that listed the same ID in
    # both fields, which would otherwise double-inject role/patch content.
    # F-E (PROGRESS-t6.md, lane head f0be2fa9): the secure-agent profile's
    # auditor / reporter roles list TRANSITIVE role-artifact reads
    # (policy-binder, approval-planner) that are not in their direct deps.
    # Without inlining those too, codex on Mac was `sed`-ing the on-disk
    # paths during the AO turn even though `write_role_artifacts()`
    # writes them only after the run completes. Augment the dep-id list
    # with any role-artifact path advertised under `task['reads']`.
    extra_dep_ids = _role_artifact_dep_ids_from_reads(intake, task)
    all_dep_ids = list(dict.fromkeys(deps + chain1_handoffs + extra_dep_ids))
    if all_dep_ids:
        prior_paths = [role_dir / f"{dep}.md" for dep in all_dep_ids]
        patch_paths = [patch_dir / f"{dep}.patch" for dep in all_dep_ids if is_mutator_task(dep)]
        profile = _active_profile()
        is_profile_role = (
            profile is not None
            and isinstance(profile.get("roles_by_id"), dict)
            and task_id in profile["roles_by_id"]
        )
        if (
            task_id in {"integrator", "evaluator-closer"}
            or _is_slice_reviewer(task_id)
            or task_id.endswith("-reviewer")
            or is_profile_role
        ):
            handoffs = []
            for dep, path in zip(all_dep_ids, prior_paths):
                # Treat zero-byte files as not-yet-written. In split-mode
                # (Phase 1.5), chain-2 evaluator-closer's prompt is rendered
                # before chain-2 integrator runs; integrator.md exists on
                # disk (touched by an earlier render-stub or chain-2 prompt
                # re-render) but its content is empty. Without this guard,
                # the evaluator sees an empty fenced block and BLOCKs with
                # "integrator handoff content is empty".
                if path.is_file() and path.stat().st_size > 0:
                    handoffs.append(fenced(path, read_for_prompt(path)))
                else:
                    handoffs.append(
                        f"### Prior Task Handoff: {dep}\n\n"
                        f"- AO dependency ordering guarantees `{dep}` completed before `{task_id}` starts.\n"
                        f"- Final role artifact path: `{display_path(path)}`.\n"
                        "- That file may not exist (or may be empty) during this provider turn because AO Operator reconstructs role artifacts from AO events after the run completes.\n"
                        "- Do not return BLOCKED solely because the role artifact file is absent or empty; use injected spec, plan, contract, status, and AO dependency ordering as the in-turn handoff."
                    )
            snippets.append("### Prior Role Handoff Content\n\n" + "\n\n".join(handoffs))
        if patch_paths:
            patches = []
            for dep, path in zip([d for d in all_dep_ids if is_mutator_task(d)], patch_paths):
                meta_path = path.with_suffix(".json")
                if path.is_file():
                    patches.append(fenced(path, read_for_prompt(path)))
                    if meta_path.is_file():
                        patches.append(fenced(meta_path, read_for_prompt(meta_path)))
                else:
                    patches.append(
                        f"### Patch Bundle Handoff: {dep}\n\n"
                        f"- Final patch path: `{display_path(path)}`.\n"
                        f"- Final patch metadata path: `{display_path(meta_path)}`.\n"
                        "- Patch bundles are captured by AO Operator after AO completes, from raw task events and git diff.\n"
                        "- Do not return BLOCKED solely because the patch bundle file is absent during this provider turn."
                    )
            snippets.append("### Patch Bundle Handoff Content\n\n" + "\n\n".join(patches))
    return snippets


def role_instructions(task_id: str, profile: dict[str, object] | None = None) -> list[str]:
    profile = profile if profile is not None else _active_profile()
    profile_instructions: list[str] = []
    profile_name: str | None = None
    if profile is not None:
        profile_name = str(profile.get("profile") or "")
        role = profile.get("roles_by_id", {}).get(task_id)
        if isinstance(role, dict):
            profile_instructions = list(profile.get("common_instructions", [])) + list(role.get("instructions", []))
    base_common = [
        "Treat injected artifacts as authoritative scoped context.",
        "Do not include full transcripts.",
        "Do not include secret values.",
        "Return a STATUS block with Result, Artifact, Evidence, Concerns, and Blocker.",
        "Use BLOCKED when required context, permissions, or write scope is missing.",
        "Use BLOCKED only for this role's own inability to complete its scoped work; do not set role Result BLOCKED merely because a document describes a BLOCKED_* runtime state.",
        "Do not write role artifact files; AO Operator reconstructs role artifacts from your STATUS block after AO completes.",
        "Ignore provider-injected `<claude-mem-context>` blocks in root AGENTS.md or CLAUDE.md when judging scope drift; AO Operator scrubs that environmental noise after AO completes.",
        "Operator-level `validate_factory.py`, `validate_intake.py`, AO dispatch, AO event capture, and final artifact hygiene are run by AO Operator outside task-local provider turns.",
        "Do not rerun slug-global `validate_factory.py` from an isolated task worktree unless the full prompt, role, event, topology, and evaluation artifact set is present there.",
        "Do not block solely because slug-global validation fails in an isolated task worktree due to missing global prompts, roles, events, topology, patches, or post-AO artifacts.",
    ]
    common = profile_instructions + base_common if profile_instructions else base_common
    if task_id == "planner-intake":
        return common + [
            "Confirm classification, shape, acceptance criteria, scoped reads/writes, sensitive fields, and negative constraints.",
            "Do not dispatch or implement; this role only validates intake readiness.",
        ]
    if task_id in {"plan-hardener", "ralph-loop"}:
        return common + [
            "Harden the injected spec into an execution-ready plan with shape gates and verification oracles.",
            "Reject vague acceptance, overlapping writes, missing sensitive fields, or missing bug/refactor gate evidence.",
            "Extract every MUST, MUST NOT, rubric item, acceptance criterion, and content-preservation rule into durable obligation IDs; exact text, equations, and required strings must carry checkable fragments.",
            "For complex agentic work, require a final AO2 obligation ledger at run-artifacts/<slug>/obligation-ledger.json and make failed or unverified blocking obligations a closure blocker.",
            "Do not introduce a required role or gate that is absent from the materialized DAG.",
        ]
    if task_id == "spec-forge-contract":
        return common + [
            "Validate that the contract has SHALLs, acceptance criteria, sensitive fields, negative constraints, and slice reads/writes.",
            "Reject fan-out if slice writes are incomplete or overlapping without an explicit integrator-owned merge contract.",
        ]
    if task_id == "factory-manager":
        return common + [
            "Choose the smallest sufficient DAG and fan-out only when slice ownership is disjoint.",
            "Use N=1 fallback when partitioning is unsafe, incomplete, or ambiguous.",
            "Do not block on ralph-loop unless the materialized DAG explicitly contains a ralph-loop task.",
            "Your role validates the dispatch decision from scoped spec, plan, contract, and topology summaries; the runner performs actual materialization, live dispatch, AO event capture, and validator execution.",
            "Return DONE or DONE_WITH_CONCERNS when scoped ownership is coherent, even though live dispatch and final validation happen outside this provider turn.",
        ]
    if is_mutator_task(task_id):
        return common + [
            "You may edit only paths listed under Scoped Writes.",
            "Before changing files, inspect the injected spec, plan, contract, and scoped write list.",
            "Keep command output short: prefer `rg`, targeted tests, and small `sed` ranges over printing large source files.",
            "Do not print generated artifact bodies; report paths and concise verification evidence so reviewer handoff context keeps the final STATUS block.",
            "If no safe edit can be made inside Scoped Writes, return BLOCKED instead of writing elsewhere.",
            "Run the narrow verification command available for this slice and report exact evidence.",
            "Prefer the slice verification listed in the contract over slug-global validation commands that require the whole run's generated artifacts.",
            "For new untracked files, `git diff --no-index /dev/null <path>` is acceptable evidence when plain `git diff` cannot see the file.",
            "Do not block on provider sandbox inability to stage files; AO Operator stages and captures the patch bundle after AO completes.",
            "Your raw output and git diff will be captured into a AO Operator patch bundle.",
        ]
    if task_id.endswith("-reviewer") or _is_slice_reviewer(task_id):
        return common + [
            "Review the matching implementer handoff content available in this prompt.",
            "If the paired factory artifact path is listed in Scoped Reads and exists in the shared worktree, inspect that artifact directly.",
            "Do not block solely because injected stdout is truncated when the paired artifact exists and the scoped verification evidence is sufficient.",
            "Do not block solely because final role artifact or patch files are absent during the provider turn; AO Operator reconstructs them after AO completes.",
            "Judge the scoped artifact against the declared slice contract and scoped writes; if a factory STATUS block overclaims extra wording that is not required by the contract, report it as a concern rather than rejecting an otherwise sufficient artifact.",
            "Reject scope drift, failed verification, or unsupported DONE claims when that evidence is available in the injected content.",
            "Treat upstream slug-global `validate_factory.py` failures caused only by missing global generated artifacts in an isolated worktree as concerns, not blockers, when the paired slice artifact and scoped verification are otherwise sufficient.",
        ]
    if task_id == "integrator":
        return common + [
            "Fan in accepted slice handoff content available in this prompt.",
            "Do not block solely because final role artifact or patch files are absent during the provider turn; AO Operator reconstructs them after AO completes.",
            "For single-slice runs, the integrator runs in the mutator worktree and may verify the implementation artifact there.",
            "For multi-slice runs, do not require every mutator artifact to exist in the integrator workspace during this provider turn; final patch fan-in is a AO Operator post-run responsibility.",
            "For untracked new files, `git diff --no-index /dev/null <path>` is sufficient integration evidence when the provider sandbox cannot stage files.",
            "Do not return BLOCKED solely because `git add`, `git add -N`, or plain `git diff --stat` cannot represent an untracked file inside the provider sandbox.",
            "Treat reviewer concerns about slug-global validation in isolated worktrees as non-blocking when they cite missing global generated artifacts rather than slice scope drift or failed scoped verification.",
            "Preserve obligation IDs from the plan into the final handoff; cite concrete files, lines, command output, or exact-fragment evidence for every obligation touched by integration.",
            "Report merge order, conflicts, skipped patches, verification evidence, and unresolved blockers.",
        ]
    if task_id == "evaluator-closer":
        profile_validation_instruction = []
        if profile_name and profile_name != "default":
            profile_validation_instruction = [
                "For non-default profile runs, validate the active profile topology with `python3 scripts/validate_factory.py --slug <slug> --profile <profile> --skip-repo-checks --allow-untracked-artifacts --allow-missing-final-evaluation`; do not fall back to baseline task names when the RunSpec contains profile role ids."
            ]
        return common + [
            "Judge final state against the original contract and acceptance criteria, not provider confidence.",
            "During the provider turn, do not reject solely because final AO events, role artifacts, or patch bundles are not yet written; AO Operator performs final closure after AO completes.",
            "When running Python closure checks from the repo root, set `PYTHONPATH=.` before pytest or verify_closure; if pytest fails with `ModuleNotFoundError: No module named 'scripts'`, retry once with `PYTHONPATH=.` before rejecting.",
            "If `python3 -m pytest` or `python3 scripts/verify_closure.py --with-pytest` fails only because that Python lacks pytest (`No module named pytest`), retry with another pytest-capable interpreter on PATH (e.g. `/opt/homebrew/bin/python3` on macOS, `python.exe` on Windows native, or the path emitted by `which python3` / `where python`) and/or the `pytest` executable on PATH before rejecting.",
            "Do not return BLOCKED solely because one Python interpreter lacks pytest when another repo-available Python or pytest executable completes the same closure checks successfully.",
            "Do not reject solely because `verify_closure.py --with-pytest` or `artifact_hygiene.py --strict` classifies the current live slug as rejected/archive-or-drop before AO Operator writes final post-AO evaluation artifacts; treat that as a timing concern when validate_factory and upstream handoffs pass.",
            "When the run is complex or an obligation ledger is present, run `python3 scripts/verify_closure.py --require-obligation-ledger` and reject any failed or unverified MUST/rubric/content-preservation obligation.",
            *profile_validation_instruction,
            "Reject blocked/rejected injected handoffs, failed verification, or write-scope drift when that evidence is available.",
        ]
    return common


_ROLE_ARTIFACT_READ_RE = re.compile(
    r"^run-artifacts/(?:[^/]+|<slug>)/roles/([^/]+)\.md$"
)


def _role_artifact_dep_ids_from_reads(intake: Intake, task: dict[str, object]) -> list[str]:
    """F-E: collect dep ids from `task['reads']` paths that match the
    role-artifact pattern. Used by both `artifact_injections()` (to inline
    transitive reads) and `_scoped_reads_with_inline_annotations()` (to
    annotate the same set of bullets). Order-preserving, dedupe-safe."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in task.get("reads", []) or []:
        rendered = str(raw).replace("<slug>", intake.slug)
        m = _ROLE_ARTIFACT_READ_RE.match(rendered)
        if not m:
            continue
        dep_id = m.group(1)
        if dep_id in seen:
            continue
        seen.add(dep_id)
        out.append(dep_id)
    return out


def _scoped_reads_with_inline_annotations(intake: Intake, task: dict[str, object]) -> list[str]:
    """F-E: render Scoped Reads with inline-handoff annotations.

    For tasks whose prior-role artifacts are inlined under
    'Injected Artifact Contents' (default-chain integrator /
    evaluator-closer / reviewer roles, plus every profile role per
    F-A wiring at `artifact_injections()`), advertise that the
    `run-artifacts/<slug>/roles/<dep>.md` Scoped Reads are
    inlined-only — codex agents on Mac were `sed`-ing those paths
    directly during the AO turn even though
    `write_role_artifacts()` does not write them until after the AO
    run completes (PROGRESS-t6.md F-E gap, lane head f0be2fa9).
    """
    task_id = str(task["id"])
    deps = [str(dep) for dep in task["deps"]]
    chain1_handoffs = [str(h) for h in task.get("chain1_handoffs", [])]
    extra_dep_ids = _role_artifact_dep_ids_from_reads(intake, task)
    all_dep_ids = list(dict.fromkeys(deps + chain1_handoffs + extra_dep_ids))
    profile = _active_profile()
    is_profile_role = (
        profile is not None
        and isinstance(profile.get("roles_by_id"), dict)
        and task_id in profile["roles_by_id"]
    )
    inlines_role_artifacts = (
        task_id in {"integrator", "evaluator-closer"}
        or _is_slice_reviewer(task_id)
        or task_id.endswith("-reviewer")
        or is_profile_role
    )
    inlined_role_paths: set[str] = set()
    if inlines_role_artifacts:
        for dep in all_dep_ids:
            inlined_role_paths.add(f"run-artifacts/{intake.slug}/roles/{dep}.md")
    out: list[str] = []
    for item in task["reads"]:
        rendered = str(item).replace("<slug>", intake.slug)
        if rendered in inlined_role_paths:
            rendered = (
                f"{rendered} (content inlined below in 'Injected Artifact Contents'; "
                f"do not read from disk during this turn — AO Operator writes role "
                f"artifacts post-AO)"
            )
        out.append(rendered)
    return out


def prompt_body(intake: Intake, task: dict[str, object], providers: dict[str, str], contract_path: Path | None) -> str:
    task_id = str(task["id"])
    workspace = Path(str(task.get("workspace") or "."))
    instructions = role_instructions(task_id)
    injections = artifact_injections(intake, task, contract_path)
    return f"""# AO Operator Role Prompt: {task_id}

Role: {task['role']}
Slug: {intake.slug}
Classification: {intake.classification}
Shape: {intake.shape}
Provider: {providers[task_id]}
Workspace: {workspace}

## Scoped Context

- Spec: docs/specs/{intake.slug}-spec.md
- Plan: docs/plans/{intake.slug}-plan.md
- Status: run-artifacts/{intake.slug}/{intake.slug}-status.md
- Contract: {rel(contract_path) if contract_path else "none"}
- Prior-role handoff content is inlined below under "Injected Artifact Contents"; do not look for `run-artifacts/<slug>/roles/*.md` on disk during this turn (those files are written post-AO).

## Embedded Task Brief

{intake.brief.strip()}

## Embedded Factory Summary

- Classification: {intake.classification}
- Shape: {intake.shape}
- Shape gate: {intake.blocker}
- Spec Forge contract: {rel(contract_path) if contract_path else "not configured"}
- Ralph Loop configured: {"yes" if task.get("ralph_loop_configured") else "no"}
- Acceptance criteria:
{bullet(intake.acceptance)}

## Role Instructions

{bullet(instructions)}

## Scoped Reads

{bullet(_scoped_reads_with_inline_annotations(intake, task))}

## Relevant Skills

{inline_skills(task_id)}

## Scoped Writes

{bullet([str(item).replace('<slug>', intake.slug) for item in task['writes']])}

## Injected Artifact Contents

{chr(10).join(injections) if injections else "- No upstream artifact content is available for this root role."}

## Boundaries

- Do not invoke Codex, Claude, AO, or any nested agent process.
- Do not read outside Scoped Reads unless needed to verify a file named in Scoped Writes.
- Do not edit outside Scoped Writes.
- Do not include full transcripts.
- Do not include secret values.
- Do not dump environment variables.
- Use OAuth CLI provider auth only.
- If a BLOCKED artifact must be written, it must be inside a declared Scoped Writes path.
- Return only the concise STATUS block below with evidence and explicit blockers.

## Required STATUS Block

Return exactly this block shape. No preface, no Markdown fence, no extra prose.

Result: DONE | DONE_WITH_CONCERNS | BLOCKED | REJECTED
Artifact: <path or event reference>
Evidence:
- <verification evidence>
Concerns:
- none | <concern>
Blocker: none | <required input>
"""


def deps_yaml(deps: list[str]) -> str:
    return "[]" if not deps else "[" + ", ".join(f'"{dep}"' for dep in deps) + "]"


def yaml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return deps_yaml([str(item) for item in value])
    text = str(value)
    if re.fullmatch(r"[A-Za-z0-9_./:-]+", text):
        return text
    return json.dumps(text)


def task_context_from(task: dict[str, object]) -> list[str]:
    task_id = str(task["id"])
    deps = [str(dep) for dep in task.get("deps", [])]
    if not deps:
        return []
    if task_id in {"integrator", "evaluator-closer"} or task_id.endswith("-reviewer") or _is_slice_reviewer(task_id):
        return deps
    return []


def runspec_body(
    intake: Intake,
    providers: dict[str, str],
    workspace: Path,
    tasks: list[dict[str, object]],
    policy_path: Path | None = None,
    remote: bool | None = None,
) -> str:
    """Render the AO RunSpec YAML body.

    `policy_path` defaults to the static `ao/policy/local-dev.yaml`. When a
    profile carries `policy_posture`, materialize() renders a slug-local
    policy YAML and passes its absolute path here so every task points at
    the profile-derived posture instead of the default-chain posture.

    `remote` (v0.2 D2) gates per-task `hostTags` emission. When True, any
    task whose role declared `host_tag` gets a `hostTags: [...]` line for
    cross-host dispatch. When False (default), no `hostTags` line is ever
    emitted and the RunSpec is byte-for-byte identical to v0.1.1 output
    for any legacy profile (parity guarantee). Pass None to fall through
    to the module-level flag set by main() via _set_active_remote.
    """
    if policy_path is None:
        resolved_policy = (ROOT / "ao/policy/local-dev.yaml").resolve()
    else:
        resolved_policy = policy_path.resolve()
    remote_active = _active_remote() if remote is None else bool(remote)
    lines = [
        "apiVersion: ao.dev/v1",
        "kind: Run",
        "metadata:",
        f"  name: {intake.slug}",
        f"  description: AO Operator full pipeline for {intake.slug}.",
        "spec:",
        "  tasks:",
    ]
    for task in tasks:
        task_id = task["id"]
        provider = providers[task_id]
        prompt_file = str(task.get("promptFile") or f"run-artifacts/{intake.slug}/prompts/{task_id}.md")
        prompt_path = Path(prompt_file)
        if not prompt_path.is_absolute():
            prompt_file = str((ROOT / prompt_path).resolve())
        task_workspace = Path(str(task.get("workspace") or workspace))
        if not task_workspace.is_absolute():
            task_workspace = (ROOT / task_workspace).resolve()
        lines.extend(
            [
                f"    - id: {task_id}",
                "      kind: agent",
                f"      deps: {deps_yaml(task['deps'])}",
            ]
        )
        if remote_active:
            host_tag = task.get("host_tag")
            if isinstance(host_tag, list) and host_tag:
                lines.append(f"      hostTags: {deps_yaml([str(t) for t in host_tag])}")
        lines.extend(
            [
                "      spec:",
                f"        provider: {provider}",
                f"        agent: {provider}-default",
                f"        promptFile: {prompt_file}",
                f"        workspace: {task_workspace}",
                f"        policyProfile: {resolved_policy}",
            ]
        )
        context_from = task_context_from(task)
        if context_from:
            lines.append(f"        contextFrom: {deps_yaml(context_from)}")
        for key, value in dict(task.get("extra_spec", {})).items():
            if key == "contextFrom" and context_from:
                continue
            lines.append(f"        {key}: {yaml_scalar(value)}")
    return "\n".join(lines) + "\n"


def status_body(
    intake: Intake,
    mode: str,
    providers: dict[str, str],
    verdict: str = "PENDING",
    ao_run: str = "none",
    topology: Path | None = None,
    contract: Path | None = None,
    materialized_workspace: str | None = None,
) -> str:
    provider_lines = [f"{task_id}: {provider}" for task_id, provider in providers.items()]
    body = f"""# {intake.slug} Status

Slug: {intake.slug}
Mode: {mode}
Classification: {intake.classification}
Shape: {intake.shape}
AO Run: {ao_run}
Factory Verdict: {verdict}

## Gate

- Blocked: {str(intake.blocked).lower()}
- Detail: {intake.blocker}

## Providers

{bullet(provider_lines)}

## Artifacts

- Spec: docs/specs/{intake.slug}-spec.md
- Plan: docs/plans/{intake.slug}-plan.md
- Topology: {rel(topology) if topology else "baseline"}
- Contract: {rel(contract) if contract else "none"}
- RunSpec: run-artifacts/{intake.slug}/{intake.slug}.runspec.yaml
- Prompts: run-artifacts/{intake.slug}/prompts/
- AO events: run-artifacts/{intake.slug}/{intake.slug}-ao-events.md
- Roles: run-artifacts/{intake.slug}/roles/
- Patch bundles: run-artifacts/{intake.slug}/patches/
- Obligation ledger: run-artifacts/{intake.slug}/obligation-ledger.json
- Evaluation: docs/evaluations/{intake.slug}-evaluation.md
"""
    if materialized_workspace:
        body += f"Materialized integrator workspace: {materialized_workspace}\n"
    return body


def materialize(
    intake: Intake,
    providers: dict[str, str],
    workspace: Path,
    tasks: list[dict[str, object]],
    topology: Path | None,
    contract: Path | None,
    mode: str = "materialized",
) -> dict[str, Path]:
    spec_path = ROOT / "docs" / "specs" / f"{intake.slug}-spec.md"
    plan_path = ROOT / "docs" / "plans" / f"{intake.slug}-plan.md"
    status_dir = ROOT / "run-artifacts" / intake.slug
    prompts_dir = status_dir / "prompts"
    runspec_path = status_dir / f"{intake.slug}.runspec.yaml"
    status_path = status_dir / f"{intake.slug}-status.md"
    events_path = status_dir / f"{intake.slug}-ao-events.md"
    evaluation_path = ROOT / "docs" / "evaluations" / f"{intake.slug}-evaluation.md"
    obligation_ledger_path = status_dir / "obligation-ledger.json"
    roles_dir = status_dir / "roles"
    patches_dir = status_dir / "patches"
    evidence_packs_dir = status_dir / "evidence-packs"

    for stale_dir in (roles_dir, patches_dir):
        if stale_dir.exists():
            shutil.rmtree(stale_dir)
        stale_dir.mkdir(parents=True, exist_ok=True)
    if events_path.exists():
        events_path.unlink()
    if evaluation_path.exists():
        evaluation_path.unlink()

    write(spec_path, spec_body(intake, providers))
    obligation_ledger.write_ledger(
        obligation_ledger_path,
        obligation_ledger.exact_fragment_ledger(
            obligation_ledger.extract_ledger(spec_path, rel(spec_path))
        ),
    )
    write(plan_path, plan_body(intake, providers, tasks, topology, contract))
    # Status doc must be written BEFORE prompt rendering. Prompts embed the
    # status doc via artifact_injections (read_for_prompt at render time);
    # if a leftover status from a prior run is on disk (e.g. "Mode: render-only"
    # restored via git checkout), prompts will inject that stale content
    # and downstream evaluator-closer turns will read the wrong mode/verdict.
    write(status_path, status_body(intake, mode, providers, topology=topology, contract=contract))
    if prompts_dir.is_dir():
        for stale_prompt in prompts_dir.glob("*.md"):
            stale_prompt.unlink()
    ralph_loop_configured = any(str(task["id"]) == "ralph-loop" for task in tasks)
    for task in tasks:
        task["ralph_loop_configured"] = ralph_loop_configured
        write(prompts_dir / f"{task['id']}.md", prompt_body(intake, task, providers, contract))
    # F-A: when the active profile carries a policy_posture block, render a
    # slug-local AO policy YAML and point this run's tasks at it. Without a
    # posture (default chain or evidence profile) the RunSpec keeps its
    # static reference to ao/policy/local-dev.yaml, byte-identical to v0.1.0.
    active = _active_profile()
    policy_path: Path | None = None
    if _profile_has_policy_posture(active):
        policy_path = status_dir / "policy.yaml"
        write(policy_path, _render_policy_yaml(active, intake.slug))
    write(runspec_path, runspec_body(intake, providers, workspace, tasks, policy_path=policy_path))

    artifacts = {
        "spec": spec_path,
        "plan": plan_path,
        "status_dir": status_dir,
        "prompts_dir": prompts_dir,
        "runspec": runspec_path,
        "status": status_path,
        "evaluation": evaluation_path,
        "events": events_path,
        "obligation_ledger": obligation_ledger_path,
        "roles_dir": roles_dir,
        "patches_dir": patches_dir,
        "evidence_packs_dir": evidence_packs_dir,
    }
    if policy_path is not None:
        artifacts["policy"] = policy_path
    if topology:
        artifacts["topology"] = topology if topology.is_absolute() else ROOT / topology
    return artifacts


def generated_artifact_paths(slug: str) -> list[Path]:
    return [
        ROOT / "docs" / "specs" / f"{slug}-spec.md",
        ROOT / "docs" / "plans" / f"{slug}-plan.md",
        ROOT / "run-artifacts" / slug,
        ROOT / "docs" / "evaluations" / f"{slug}-evaluation.md",
    ]


def existing_generated_artifacts(slug: str) -> list[str]:
    return [rel(path) for path in generated_artifact_paths(slug) if path.exists()]


def profile_path_for_gate(profile_name: str) -> Path | None:
    if not profile_name or profile_name == "default":
        path = PROFILES_DIR / "default.json"
        return path if path.is_file() else None
    if ":" in profile_name:
        namespace, name = profile_name.split(":", 1)
        path = PROFILES_DIR / namespace / f"{name}.json"
        return path if path.is_file() else None
    for path in (PROFILES_DIR / f"{profile_name}.json", PROFILES_DIR / "starters" / f"{profile_name}.json"):
        if path.is_file():
            return path
    return None


def gate_b_intake_artifacts(paths: dict[str, Path], contract: Path | None) -> list[Path]:
    artifacts = [paths["spec"]]
    if contract:
        artifacts.append(contract if contract.is_absolute() else ROOT / contract)
    return artifacts


def run_gate_b_strict(
    *,
    intake: Intake,
    paths: dict[str, Path],
    profile_name: str,
    contract: Path | None,
    partition_slices: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    report = gate_b.run_gate(
        repo=ROOT,
        slug=intake.slug,
        intake_artifacts=gate_b_intake_artifacts(paths, contract),
        profile_path=profile_path_for_gate(profile_name),
        partition_slices=partition_slices,
    )
    write_json(paths["status_dir"] / "gate-b.json", report)
    return report


def run_gate_r_strict(*, intake: Intake, paths: dict[str, Path]) -> dict[str, object]:
    report = gate_r.run_gate(
        repo=ROOT,
        slug=intake.slug,
        gate_b_path=paths["status_dir"] / "gate-b.json",
    )
    write_json(paths["status_dir"] / "gate-r.json", report)
    return report


def print_gate_errors(gate_name: str, report: dict[str, object]) -> None:
    for error in report.get("errors", []):
        print(f"factory_run.py: {gate_name} blocked: {error}", file=sys.stderr)


def claude_mem_context_paths(root: Path) -> list[str]:
    polluted: list[str] = []
    for name in ("AGENTS.md", "CLAUDE.md"):
        path = root / name
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "<claude-mem-context>" in body:
            polluted.append(path.relative_to(root).as_posix())
    return polluted


def scrub_root_claude_mem_context(root: Path) -> list[str]:
    scrubbed: list[str] = []
    for name in ("AGENTS.md", "CLAUDE.md"):
        path = root / name
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "<claude-mem-context>" not in content:
            continue
        cleaned = _CLAUDE_MEM_BLOCK_RE.sub("\n", content).rstrip() + "\n"
        if cleaned != content:
            path.write_text(cleaned, encoding="utf-8")
            scrubbed.append(path.relative_to(root).as_posix())
    return scrubbed


def workspace_claude_mem_blocker(workspace_root: Path) -> str | None:
    polluted = claude_mem_context_paths(workspace_root)
    if not polluted:
        return None
    return (
        "claude-mem context pollution detected in workspace "
        f"{workspace_root}: {', '.join(polluted)}; rerun with "
        "--scrub-root-context or remove the injected <claude-mem-context> "
        "block before running AO Operator"
    )


def preflight_blockers(slug: str, *, overwrite_artifacts: bool) -> list[str]:
    blockers: list[str] = []
    polluted = claude_mem_context_paths(ROOT)
    if polluted:
        blockers.append(
            "claude-mem context pollution detected in "
            + ", ".join(polluted)
            + "; remove the injected <claude-mem-context> block before running AO Operator"
        )

    existing = existing_generated_artifacts(slug)
    if existing and not overwrite_artifacts:
        blockers.append(
            "generated artifacts already exist for slug "
            f"{slug!r}: {', '.join(existing)}; rerun with --overwrite-artifacts "
            "only when intentionally replacing or continuing that slug"
        )
    return blockers


def max_live_tasks() -> int:
    raw = os.environ.get(MAX_LIVE_TASKS_ENV, str(DEFAULT_MAX_LIVE_TASKS))
    try:
        limit = int(raw)
    except ValueError:
        return DEFAULT_MAX_LIVE_TASKS
    return max(1, limit)


def live_run_blockers(tasks: list[dict[str, object]], *, run: bool) -> list[str]:
    if not run or os.environ.get(ALLOW_LARGE_LIVE_RUN_ENV) == "1":
        return []
    limit = max_live_tasks()
    task_count = len(tasks)
    if task_count <= limit:
        return []
    return [
        f"live run task count {task_count} exceeds {MAX_LIVE_TASKS_ENV}={limit}; "
        "use a bounded live topology first or set "
        f"{ALLOW_LARGE_LIVE_RUN_ENV}=1 with documented provider-limit evidence"
    ]


def materialize_render_only_stubs(paths: dict[str, Path], tasks: list[dict[str, object]]) -> int:
    for directory in (paths["roles_dir"], paths["patches_dir"]):
        directory.mkdir(parents=True, exist_ok=True)
        for stale in directory.glob("*"):
            if stale.is_file():
                stale.unlink()
    write(paths["events"], "")
    for task in tasks:
        write(paths["roles_dir"] / f"{task['id']}.md", "")
    return len(list(paths["prompts_dir"].glob("*.md")))


def command_text(cmd: list[str]) -> str:
    return " ".join(cmd)


def git_available(workspace_root: Path) -> bool:
    return shutil.which("git") is not None and (workspace_root / ".git").exists()


def _safe_lease_name(task_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", task_id)


def _worktree_lease_dir(slug: str) -> Path:
    return WORKTREE_ROOT / slug / WORKTREE_LEASE_DIRNAME


def _worktree_lease_path(slug: str, task_id: str) -> Path:
    return _worktree_lease_dir(slug) / f"{_safe_lease_name(task_id)}.json"


def _git_head_short(workspace_root: Path) -> str | None:
    result = run_command(
        ["git", "rev-parse", "--short=8", "HEAD"],
        workspace_root,
        os.environ.copy(),
        timeout=30,
    )
    if result.returncode != 0:
        return None
    head = result.stdout.strip()
    return head or None


def write_worktree_lease(slug: str, task_id: str, path: Path, workspace_root: Path, *, purpose: str) -> Path:
    lease = _worktree_lease_path(slug, task_id)
    lease.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": WORKTREE_LEASE_SCHEMA,
        "slug": slug,
        "task_id": task_id,
        "purpose": purpose,
        "path": str(path),
        "workspace_root": str(workspace_root),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "stale_after_seconds": factory_v3_config.WORKTREE_LEASE_STALE_AFTER_SECONDS,
        "head": _git_head_short(workspace_root),
        "state": "leased",
    }
    lease.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return lease


def clear_worktree_lease(slug: str, task_id: str) -> None:
    lease = _worktree_lease_path(slug, task_id)
    if lease.exists():
        lease.unlink()
    lease_dir = lease.parent
    if lease_dir.is_dir() and not any(lease_dir.iterdir()):
        lease_dir.rmdir()


def cleanup_worktree_leases(slug: str, workspace_root: Path) -> list[str]:
    lease_dir = _worktree_lease_dir(slug)
    if not lease_dir.is_dir():
        return []
    notes: list[str] = []
    for lease in sorted(lease_dir.glob("*.json")):
        task_id = lease.stem
        try:
            payload = json.loads(lease.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            lease.unlink(missing_ok=True)
            notes.append(f"{task_id}: unreadable worktree lease removed: {exc}")
            continue
        if isinstance(payload, dict):
            task_id = str(payload.get("task_id") or task_id)
            leased_path = payload.get("path")
        else:
            leased_path = None
        if isinstance(leased_path, str) and leased_path:
            _remove_worktree(Path(leased_path), workspace_root)
            notes.append(f"{task_id}: stale worktree lease cleaned {leased_path}")
        else:
            notes.append(f"{task_id}: stale worktree lease metadata removed")
        lease.unlink(missing_ok=True)
    if lease_dir.is_dir() and not any(lease_dir.iterdir()):
        lease_dir.rmdir()
    return notes


def prepare_worktrees(slug: str, tasks: list[dict[str, object]], enabled: bool, workspace_root: Path) -> list[str]:
    if not enabled:
        return ["isolated worktrees disabled for dry-run"]
    if not git_available(workspace_root):
        return ["git worktree isolation unavailable; using root workspace"]
    notes: list[str] = cleanup_worktree_leases(slug, workspace_root)
    root = WORKTREE_ROOT / slug
    if root.exists():
        for child in root.iterdir():
            if child.is_dir() and child.name != WORKTREE_LEASE_DIRNAME:
                _remove_worktree(child, workspace_root)
                notes.append(f"unleased stale worktree cleaned {child}")
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    mutator_workspaces: dict[str, str] = {}
    for task in tasks:
        task_id = str(task["id"])
        if not is_mutator_task(task_id):
            continue
        path = root / task_id
        result = run_command(
            ["git", "worktree", "add", "--detach", str(path), "HEAD"],
            workspace_root,
            os.environ.copy(),
            timeout=180,
        )
        if result.returncode == 0:
            task["workspace"] = str(path)
            mutator_workspaces[task_id] = str(path)
            write_worktree_lease(slug, task_id, path, workspace_root, purpose="mutator")
            notes.append(f"{task_id}: isolated worktree {path}")
        else:
            task["workspace"] = str(workspace_root)
            notes.append(f"{task_id}: worktree creation failed; using root workspace: {result.stderr.strip() or result.stdout.strip()}")
    if len(mutator_workspaces) == 1:
        workspace = next(iter(mutator_workspaces.values()))
        for task in tasks:
            task_id = str(task["id"])
            if task_id in {"reviewer-slice", "integrator", "evaluator-closer"}:
                task["workspace"] = workspace
                notes.append(f"{task_id}: shares single mutator worktree {workspace}")
    for task in tasks:
        task_id = str(task["id"])
        if not task_id.endswith("-reviewer"):
            continue
        factory_id = task_id.removesuffix("-reviewer") + "-factory"
        workspace = mutator_workspaces.get(factory_id)
        if workspace:
            task["workspace"] = workspace
            notes.append(f"{task_id}: shares matching mutator worktree {workspace}")
    for task in tasks:
        task_id = str(task["id"])
        if not task_id.startswith("reviewer-slice-"):
            continue
        impl_id = task_id.replace("reviewer-slice-", "implementer-slice-", 1)
        workspace = mutator_workspaces.get(impl_id)
        if workspace:
            task["workspace"] = workspace
            notes.append(f"{task_id}: shares matching slice mutator worktree {workspace}")
        else:
            notes.append(f"{task_id}: no worktree found for {impl_id}; falling back to root workspace")
    return notes or ["no mutator tasks required isolated worktrees"]


def _remove_worktree(target: Path, workspace_root: Path) -> None:
    """Best-effort removal of an integrator worktree. Used by
    materialize_integrator_workspace on partial-failure paths so we
    don't leave orphan worktrees on disk."""
    run_command(
        ["git", "worktree", "remove", "--force", str(target)],
        workspace_root,
        os.environ.copy(),
        timeout=180,
    )
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)


def materialize_integrator_workspace(
    slug: str,
    slice_ids: list[str],
    patches_dir: Path,
    workspace_root: Path,
) -> tuple[Path | None, list[str], list[str]]:
    """Create an integrator worktree and apply all slice patches into it.

    Returns (path, notes, blockers).
    - On success: path is the materialized worktree, blockers is empty.
    - On failure: path is None, blockers explains why; chain 2 must NOT
      be dispatched.

    Used by the N>=2 path in main() between chain 1 and chain 2 of the
    split AO dispatch (SDD 09).
    """
    notes: list[str] = []
    blockers: list[str] = []
    if not git_available(workspace_root):
        return None, notes, ["git worktree creation unavailable; cannot materialize integrator workspace"]
    target = WORKTREE_ROOT / slug / "integrator"
    if target.exists():
        _remove_worktree(target, workspace_root)
        clear_worktree_lease(slug, "integrator")
    target.parent.mkdir(parents=True, exist_ok=True)
    create = run_command(
        ["git", "worktree", "add", "--detach", str(target), "HEAD"],
        workspace_root,
        os.environ.copy(),
        timeout=180,
    )
    if create.returncode != 0:
        return None, notes, [
            f"integrator worktree creation failed: {create.stderr.strip() or create.stdout.strip()}"
        ]
    write_worktree_lease(slug, "integrator", target, workspace_root, purpose="integrator")
    notes.append(f"integrator: materialized worktree {target}")
    for slice_id in slice_ids:
        patch = patches_dir / f"{slice_id}.patch"
        if not patch.is_file():
            _remove_worktree(target, workspace_root)
            clear_worktree_lease(slug, "integrator")
            return None, notes, [f"integrator materialization: patch missing for {slice_id}: {patch}"]
        patch_text = patch.read_text(encoding="utf-8")
        if not patch_text.strip():
            notes.append(f"integrator: skipped empty patch for {slice_id}")
            continue
        apply = run_command(
            ["git", "apply", "--index", str(patch)],
            target,
            os.environ.copy(),
            timeout=60,
        )
        if apply.returncode != 0:
            _remove_worktree(target, workspace_root)
            clear_worktree_lease(slug, "integrator")
            return None, notes, [
                f"integrator materialization: git apply failed for {slice_id}: "
                f"{apply.stderr.strip() or apply.stdout.strip()}"
            ]
        notes.append(f"integrator: applied {slice_id} patch")
    return target, notes, blockers


def sync_generated_artifacts_to_worktrees(
    paths: dict[str, Path], tasks: list[dict[str, object]], contract: Path | None, workspace_root: Path
) -> None:
    tasks_by_workspace: dict[Path, list[dict[str, object]]] = {}
    for task in tasks:
        workspace = Path(str(task.get("workspace") or workspace_root))
        if workspace.resolve() in {workspace_root.resolve(), ROOT.resolve()} or not workspace.is_dir():
            continue
        tasks_by_workspace.setdefault(workspace.resolve(), []).append(task)

    for workspace, workspace_tasks in tasks_by_workspace.items():
        target_status_dir = workspace / rel(paths.get("status_dir", paths["status"].parent))
        for stale_name in ("roles", "patches"):
            stale_dir = target_status_dir / stale_name
            if stale_dir.exists():
                shutil.rmtree(stale_dir)
        if "events" in paths:
            target_events = workspace / rel(paths["events"])
            if target_events.exists():
                target_events.unlink()
        for key in ["spec", "plan", "runspec", "status"]:
            source = paths[key]
            target = workspace / rel(source)
            if source.resolve() == target.resolve():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        target_prompts = workspace / rel(paths["prompts_dir"])
        if paths["prompts_dir"].resolve() == target_prompts.resolve():
            target_prompts.mkdir(parents=True, exist_ok=True)
        elif target_prompts.exists():
            shutil.rmtree(target_prompts)
            target_prompts.mkdir(parents=True, exist_ok=True)
        else:
            target_prompts.mkdir(parents=True, exist_ok=True)
        for task in workspace_tasks:
            task_id = str(task["id"])
            source_prompt = paths["prompts_dir"] / f"{task_id}.md"
            if not source_prompt.is_file():
                continue
            shutil.copy2(source_prompt, target_prompts / source_prompt.name)
        sync_agent_manifests_to(workspace)
        if contract:
            contract_path = contract if contract.is_absolute() else ROOT / contract
            if contract_path.is_file():
                target = workspace / rel(contract_path)
                if contract_path.resolve() != target.resolve():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(contract_path, target)
    topology_path = paths.get("topology")
    if topology_path and topology_path.is_file():
        target = workspace / rel(topology_path)
        if topology_path.resolve() != target.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(topology_path, target)


def task_scoped_read_source_roots() -> list[Path]:
    roots: list[Path] = [ROOT]
    runtime = os.environ.get("FACTORY_V3_AO_RUNTIME_PATH")
    if runtime:
        runtime_root = Path(runtime).expanduser().resolve()
        if runtime_root.is_dir() and runtime_root not in [root.resolve() for root in roots]:
            roots.append(runtime_root)
    return roots


def _copy_scoped_read_from_roots(read_path: str, workspace: Path, source_roots: list[Path]) -> str | None:
    normalized = read_path.strip()
    if (
        not normalized
        or normalized == "task brief"
        or normalized.endswith(" artifact")
        or normalized in {"spec", "plan", "AO events", "role artifacts", "accepted slice artifacts"}
        or Path(normalized).is_absolute()
    ):
        return None

    relative = normalized.rstrip("/")
    for root in source_roots:
        source = root / relative
        if not source.exists():
            continue
        target = workspace / relative
        if source.resolve() == target.resolve():
            return None
        if source.is_dir():
            if target.exists():
                shutil.rmtree(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target)
            return "/" + relative + "/"
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            return "/" + relative
    return None


def sync_task_scoped_reads_to_worktrees(tasks: list[dict[str, object]], workspace_root: Path, slug: str) -> None:
    """Copy each assigned task's declared read files into its isolated worktree.

    Contract-backed live runs may ask AO Operator roles to inspect files from
    the external AO runtime repository while the role itself executes inside a
    AO Operator git worktree. Materialize only the declared reads, and git-ignore
    them so provider patch bundles remain limited to scoped writes.
    """
    source_roots = task_scoped_read_source_roots()
    copied_by_workspace: dict[Path, set[str]] = {}
    for task in tasks:
        workspace = Path(str(task.get("workspace") or workspace_root))
        if workspace.resolve() == workspace_root.resolve() or not workspace.is_dir():
            continue
        workspace_key = workspace.resolve()
        copied = copied_by_workspace.setdefault(workspace_key, set())
        for item in task.get("reads", []):
            read_path = str(item).replace("<slug>", slug)
            pattern = _copy_scoped_read_from_roots(read_path, workspace, source_roots)
            if pattern:
                copied.add(pattern)

    for workspace, patterns in copied_by_workspace.items():
        if patterns:
            add_target_git_excludes(workspace, sorted(patterns))


def target_generated_artifact_excludes(paths: dict[str, Path], contract: Path | None) -> list[str]:
    exclude_paths = [
        "/" + rel(paths["spec"]),
        "/" + rel(paths["plan"]),
        "/" + rel(paths["runspec"]),
        "/" + rel(paths["status"]),
        "/" + rel(paths["prompts_dir"]) + "/",
    ]
    if "evaluation" in paths:
        exclude_paths.append("/" + rel(paths["evaluation"]))
    if contract:
        contract_path = contract if contract.is_absolute() else ROOT / contract
        if contract_path.is_file():
            exclude_paths.append("/" + rel(contract_path))
    topology_path = paths.get("topology")
    if topology_path and topology_path.is_file():
        exclude_paths.append("/" + rel(topology_path))
    return exclude_paths


def add_target_generated_artifact_excludes(workspace: Path, paths: dict[str, Path], contract: Path | None) -> None:
    add_target_git_excludes(workspace, target_generated_artifact_excludes(paths, contract))


def add_target_git_excludes(workspace: Path, patterns: list[str]) -> None:
    if not git_available(workspace):
        return
    git_path = run_command(
        ["git", "rev-parse", "--git-path", "info/exclude"],
        workspace,
        os.environ.copy(),
        timeout=30,
    )
    if git_path.returncode != 0:
        return
    exclude_file = Path(git_path.stdout.strip())
    if not exclude_file.is_absolute():
        exclude_file = workspace / exclude_file
    exclude_file.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude_file.read_text(encoding="utf-8") if exclude_file.exists() else ""
    lines = existing.splitlines()
    for pattern in patterns:
        if pattern not in lines:
            lines.append(pattern)
    exclude_file.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def sync_generated_artifacts_to_workspace_root(
    paths: dict[str, Path], workspace_root: Path, contract: Path | None
) -> None:
    if workspace_root.resolve() == ROOT.resolve() or not workspace_root.is_dir():
        return
    add_target_generated_artifact_excludes(workspace_root, paths, contract)
    for key in ["spec", "plan", "runspec", "status"]:
        source = paths[key]
        target = workspace_root / rel(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    source_prompts = paths["prompts_dir"]
    target_prompts = workspace_root / rel(source_prompts)
    if target_prompts.exists():
        shutil.rmtree(target_prompts)
    shutil.copytree(source_prompts, target_prompts)
    sync_agent_manifests_to(workspace_root)
    if contract:
        contract_path = contract if contract.is_absolute() else ROOT / contract
        if contract_path.is_file():
            target = workspace_root / rel(contract_path)
            if contract_path.resolve() != target.resolve():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(contract_path, target)
    topology_path = paths.get("topology")
    if topology_path and topology_path.is_file():
        target = workspace_root / rel(topology_path)
        if topology_path.resolve() != target.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(topology_path, target)


def sync_scoped_reads_to_workspace_root(intake: Intake, workspace_root: Path) -> None:
    if workspace_root.resolve() == ROOT.resolve() or not workspace_root.is_dir():
        return
    copied_patterns: list[str] = []
    for item in intake.scoped_reads:
        read_path = str(item).replace("<slug>", intake.slug).strip()
        if not read_path or read_path == "task brief" or Path(read_path).is_absolute():
            continue
        source = ROOT / read_path.rstrip("/")
        if not source.exists():
            continue
        target = workspace_root / read_path.rstrip("/")
        if source.is_dir():
            if target.exists():
                shutil.rmtree(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target)
            copied_patterns.append("/" + read_path.rstrip("/") + "/")
        elif source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied_patterns.append("/" + read_path.rstrip("/"))
    if copied_patterns:
        add_target_git_excludes(workspace_root, copied_patterns)


def sync_factory_helper_scripts_to_workspace_root(workspace_root: Path) -> None:
    if workspace_root.resolve() == ROOT.resolve() or not workspace_root.is_dir():
        return
    helpers = ["scripts/validate_intake.py", "scripts/verify_closure.py"]
    copied_patterns: list[str] = []
    for helper in helpers:
        source = ROOT / helper
        if not source.is_file():
            continue
        target = workspace_root / helper
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied_patterns.append("/" + helper)
    if copied_patterns:
        add_target_git_excludes(workspace_root, copied_patterns)


def sync_agent_manifests_to(target: Path) -> None:
    for tool_dir in [".codex", ".claude", ".antigravity"]:
        source = ROOT / tool_dir / "agents"
        if not source.is_dir():
            continue
        destination = target / tool_dir / "agents"
        if destination.exists():
            for source_file in source.rglob("*"):
                if not source_file.is_file():
                    continue
                relative = source_file.relative_to(source)
                target_file = destination / relative
                if target_file.exists():
                    continue
                target_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, target_file)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)


def snapshot_worktree_baselines(tasks: list[dict[str, object]], workspace_root: Path) -> list[str]:
    """Commit the synced-artifacts state in each mutator worktree.

    sync_generated_artifacts_to_worktrees() copies factory-generated specs,
    plans, runspecs, status, and prompts into each per-mutator worktree as
    untracked files. Without snapshotting, those files appear in the
    post-provider git diff and pollute the patch bundle (or, worse, hide
    the provider's actual edits when `git diff` ignores untracked entries).

    A no-effect-but-author commit anchors HEAD at the synced state so the
    later `git diff --cached` in git_diff() captures only what the provider
    produced.
    """
    notes: list[str] = []
    for task in tasks:
        task_id = str(task["id"])
        if not is_mutator_task(task_id):
            continue
        workspace = Path(str(task.get("workspace") or workspace_root))
        if workspace.resolve() == workspace_root.resolve() or not workspace.is_dir():
            continue
        env = os.environ.copy()
        env.setdefault("GIT_AUTHOR_NAME", "ao-operator")
        env.setdefault("GIT_AUTHOR_EMAIL", "ao-operator@local")
        env.setdefault("GIT_COMMITTER_NAME", "ao-operator")
        env.setdefault("GIT_COMMITTER_EMAIL", "ao-operator@local")
        add_rc = run_command(["git", "add", "-A"], workspace, env, timeout=60)
        if add_rc.returncode != 0:
            notes.append(f"{task_id}: snapshot git add failed: {add_rc.stderr.strip() or add_rc.stdout.strip()}")
            continue
        commit_rc = run_command(
            ["git", "commit", "--allow-empty", "-m", "ao-operator pre-provider snapshot"],
            workspace,
            env,
            timeout=60,
        )
        if commit_rc.returncode == 0:
            notes.append(f"{task_id}: snapshot committed in {workspace}")
        else:
            notes.append(
                f"{task_id}: snapshot commit failed: {commit_rc.stderr.strip() or commit_rc.stdout.strip()}"
            )
    return notes or ["no mutator tasks required snapshot"]


def run_command(cmd: list[str], cwd: Path, env: dict[str, str], timeout: int = 3600) -> subprocess.CompletedProcess[str]:
    return factory_ao_adapter.run_command(cmd, cwd, env, timeout=timeout)


def ao_binary() -> str:
    return factory_ao_adapter.resolve_ao_binary(default_runtime=AO_RUNTIME_DEFAULT)


def ensure_ao_home(ao_bin: str, ao_home: Path) -> None:
    factory_ao_adapter.ensure_ao_home(ao_bin, ao_home, cwd=ROOT)


def extract_run_id(text: str) -> str:
    return factory_ao_adapter.extract_run_id(text)


def collect_events(ao_bin: str, ao_home: Path, run_id: str) -> subprocess.CompletedProcess[str] | None:
    return factory_ao_adapter.collect_events(ao_bin, ao_home, run_id, cwd=ROOT)


def event_summary(text: str) -> dict[str, object]:
    return factory_event_normalizer.event_summary(text)


def failure_diagnostics_evidence(event_text: str) -> list[str]:
    return factory_event_normalizer.failure_diagnostics_evidence(event_text)


def write_events(path: Path, run_id: str, run_result: subprocess.CompletedProcess[str], events_result: subprocess.CompletedProcess[str] | None) -> str:
    event_text = events_result.stdout if events_result else ""
    summary = event_summary(event_text)
    body = f"""# AO Events

Run id: {run_id}
Run command exit: {run_result.returncode}
Events command exit: {events_result.returncode if events_result else "not-run"}

## Summary

- Task completed events: {summary["task_completed"]}
- Task failed events: {summary["task_failed"]}
- Policy decisions: {summary["policy_decisions"]}
- stdout events: {summary["stdout_events"]}
- stderr events: {summary["stderr_events"]}
- Event lines: {summary["lines"]}
- Normalized reason counts: {json.dumps(summary["normalized_reason_counts"], sort_keys=True)}
- Primary normalized reason: {summary["primary_normalized_reason"] or "none"}

## Run stdout

```text
{run_result.stdout.strip()}
```

## Run stderr

```text
{run_result.stderr.strip()}
```

## Events stdout

```text
{event_text.strip()}
```
"""
    write(path, body)
    return event_text


def task_seen(event_text: str, task_id: str) -> bool:
    return factory_event_normalizer.task_seen(event_text, task_id)


def status_block(text: str) -> str:
    return factory_event_normalizer.status_block(text)


def status_from_event_object(value: object) -> str:
    return factory_event_normalizer.status_from_event_object(value)


def extract_agent_status(event_text: str, task_id: str) -> str:
    return factory_event_normalizer.extract_agent_status(event_text, task_id)


def extract_task_events(event_text: str, task_id: str) -> str:
    return factory_event_normalizer.extract_task_events(event_text, task_id)


def result_from_status(status_text: str, fallback_completed: bool) -> str:
    return factory_event_normalizer.result_from_status(status_text, fallback_completed)


def scrub_claude_mem_pollution(workspace: Path) -> list[str]:
    """Strip <claude-mem-context>...</claude-mem-context> blocks injected
    into worktree files by the claude-mem plugin as a side effect of running
    provider CLIs inside the worktree. These blocks are environmental noise,
    not slice work, and create false patch conflicts when the integrator
    applies multiple slice patches that all touch the same file (typically
    AGENTS.md or CLAUDE.md).

    For any contaminated file that EXISTS at HEAD without the block, the
    fastest, safest fix is a full revert (`git checkout HEAD -- <file>`):
    claude-mem is purely additive on existing files, so HEAD is the
    canonical clean state. Surgical regex stripping risks normalizing
    line endings or stripping legitimate trailing whitespace differences.

    For a NEW file (didn't exist at HEAD) that the provider created
    containing only a claude-mem block, strip the block via regex; if
    nothing meaningful remains, delete the file.

    Returns the list of files scrubbed.
    """
    if not workspace.is_dir():
        return []
    status = run_command(
        ["git", "status", "--short"],
        workspace,
        os.environ.copy(),
        timeout=30,
    )
    if status.returncode != 0:
        return []
    scrubbed: list[str] = []
    for line in status.stdout.splitlines():
        if len(line) < 4:
            continue
        path_str = line[3:].strip()
        if " -> " in path_str:
            path_str = path_str.split(" -> ", 1)[1]
        path_str = path_str.strip('"')
        if path_str == "scripts/factory_run.py":
            # This file contains the literal claude-mem sentinel in the
            # scrubber regex below; applying that regex to this source file
            # corrupts the pattern itself.
            continue
        path = workspace / path_str
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "<claude-mem-context>" not in content:
            continue
        head_show = run_command(
            ["git", "show", f"HEAD:{path_str}"],
            workspace,
            os.environ.copy(),
            timeout=30,
        )
        head_existed = head_show.returncode == 0
        head_clean = head_existed and "<claude-mem-context>" not in head_show.stdout
        if head_clean:
            revert = run_command(
                ["git", "checkout", "HEAD", "--", path_str],
                workspace,
                os.environ.copy(),
                timeout=30,
            )
            if revert.returncode == 0:
                scrubbed.append(path_str)
                continue
        cleaned = _CLAUDE_MEM_BLOCK_RE.sub("", content)
        if not cleaned.strip():
            path.unlink()
            scrubbed.append(path_str)
        elif cleaned != content:
            if not cleaned.endswith("\n"):
                cleaned += "\n"
            path.write_text(cleaned, encoding="utf-8")
            scrubbed.append(path_str)
    return scrubbed


def git_diff(
    workspace: Path,
    exclude_paths: list[str],
    force_add_paths: list[str] | None = None,
) -> tuple[int, str, str]:
    if not workspace.is_dir():
        return 1, "", f"workspace missing: {workspace}"
    # Strip claude-mem environmental pollution from any modified file before
    # staging. See scrub_claude_mem_pollution() for the why.
    scrub_claude_mem_pollution(workspace)
    # Stage every change (including untracked new files the provider created)
    # so the diff captures new-file creation, not just modifications. This
    # only works correctly because snapshot_worktree_baselines() committed
    # the post-sync, pre-provider state to HEAD; everything staged here is
    # provider-produced.
    add_result = run_command(["git", "add", "-A"], workspace, os.environ.copy(), timeout=60)
    if add_result.returncode != 0:
        return add_result.returncode, "", f"git add failed: {add_result.stderr or add_result.stdout}"
    for raw_path in force_add_paths or []:
        force_path = raw_path.strip().strip("/")
        if not force_path or Path(force_path).is_absolute():
            continue
        if not (workspace / force_path).exists():
            continue
        force_result = run_command(["git", "add", "-f", "--", force_path], workspace, os.environ.copy(), timeout=60)
        if force_result.returncode != 0:
            return force_result.returncode, "", f"git add -f failed for {force_path}: {force_result.stderr or force_result.stdout}"
    pathspec = [".", *[f":(exclude){path}" for path in exclude_paths]]
    result = run_command(["git", "diff", "--binary", "--cached", "--", *pathspec], workspace, os.environ.copy(), timeout=240)
    return result.returncode, result.stdout, result.stderr


ROOT_INSTRUCTION_FILES = {"AGENTS.md", "CLAUDE.md"}


def task_write_scope_owns_path(task: dict[str, object], path: str) -> bool:
    normalized = path.strip().strip("/")
    for item in task.get("writes", []):
        candidate = str(item).replace("<slug>", "").strip().strip("/")
        if candidate in {normalized, "."}:
            return True
    return False


def environmental_exclude_paths(task: dict[str, object]) -> list[str]:
    return [
        path
        for path in sorted(ROOT_INSTRUCTION_FILES)
        if not task_write_scope_owns_path(task, path)
    ]


def git_status(workspace: Path) -> str:
    if not workspace.is_dir():
        return f"workspace missing: {workspace}"
    result = run_command(["git", "status", "--short"], workspace, os.environ.copy(), timeout=120)
    return result.stdout.strip() if result.returncode == 0 else (result.stderr.strip() or result.stdout.strip())


def write_patch_bundles(paths: dict[str, Path], intake: Intake, tasks: list[dict[str, object]], event_text: str) -> dict[str, dict[str, object]]:
    patches_dir = paths["patches_dir"]
    patches_dir.mkdir(parents=True, exist_ok=True)
    bundles: dict[str, dict[str, object]] = {}
    for task in tasks:
        task_id = str(task["id"])
        if not is_mutator_task(task_id):
            continue
        workspace = Path(str(task.get("workspace") or ROOT))
        status_text = extract_agent_status(event_text, task_id)
        raw_events = extract_task_events(event_text, task_id)
        exclude_paths = [
            f"run-artifacts/{intake.slug}/",
            f"docs/evaluations/{intake.slug}-evaluation.md",
            *environmental_exclude_paths(task),
        ]
        scoped_write_paths = [str(item).replace("<slug>", intake.slug) for item in task["writes"]]
        diff_exit, diff_text, diff_err = git_diff(workspace, exclude_paths, force_add_paths=scoped_write_paths)
        status = git_status(workspace)
        patch_path = patches_dir / f"{task_id}.patch"
        events_path = patches_dir / f"{task_id}-events.txt"
        meta_path = patches_dir / f"{task_id}.json"
        write(patch_path, diff_text)
        write(events_path, raw_events or "No task-scoped AO events captured.\n")
        meta = {
            "task_id": task_id,
            "workspace": str(workspace),
            "patch": rel(patch_path),
            "raw_events": rel(events_path),
            "status_result": result_from_status(status_text, task_seen(event_text, task_id)),
            "status_captured": bool(status_text),
            "diff_exit": diff_exit,
            "diff_bytes": len(diff_text.encode("utf-8")),
            "git_status": status,
            "diff_stderr": diff_err.strip(),
            "scoped_writes": scoped_write_paths,
        }
        write(meta_path, json.dumps(meta, indent=2) + "\n")
        bundles[task_id] = meta
    return bundles


def write_role_artifacts(
    paths: dict[str, Path],
    intake: Intake,
    event_text: str,
    ao_run: str,
    tasks: list[dict[str, object]],
    patch_bundles: dict[str, dict[str, object]] | None = None,
) -> list[Path]:
    roles_dir = paths["roles_dir"]
    written: list[Path] = []
    patch_bundles = patch_bundles or {}
    for task in tasks:
        task_id = task["id"]
        artifact = roles_dir / f"{task_id}.md"
        completed = task_seen(event_text, task_id)
        status_text = extract_agent_status(event_text, task_id)
        result = result_from_status(status_text, completed)
        evidence = [
            f"AO run: {ao_run}",
            f"Prompt: run-artifacts/{intake.slug}/prompts/{task_id}.md",
            f"RunSpec task: {task_id}",
        ]
        if completed:
            evidence.append("AO task.completed event observed.")
        else:
            evidence.append("AO events were captured, but task-specific completion could not be isolated from textual output.")
        if status_text:
            evidence.append("Agent STATUS block captured from AO event stream.")
        else:
            evidence.append("Agent STATUS block missing or malformed; AO Operator applied STATUS fallback.")
        if task_id in patch_bundles:
            patch = patch_bundles[task_id]
            evidence.append(f"Patch bundle: {patch['patch']}")
            evidence.append(f"Patch bytes: {patch['diff_bytes']}")
        body = f"""# {task_id} Role Artifact

Result: {result}
Artifact: run-artifacts/{intake.slug}/roles/{task_id}.md
Evidence:
{bullet(evidence)}
Concerns:
- {"none" if completed else "task completion was inferred from aggregate AO completion evidence"}
Blocker: {"none" if result not in {"BLOCKED", "REJECTED"} else "Agent returned blocked or rejected STATUS; see AO events."}

## Captured STATUS

```text
{status_text or "No agent STATUS text captured."}
```

## Runtime Capture

- Workspace: {_runtime_capture_workspace_label(task)}
- Patch bundle: {patch_bundles.get(task_id, {}).get("patch", "not applicable")}
- Raw task events: {patch_bundles.get(task_id, {}).get("raw_events", "not applicable")}
"""
        write(artifact, body)
        written.append(artifact)
    return written


def _declared_materialized_artifact_path(raw_path: object, slug: str) -> Path | None:
    path_text = str(raw_path).replace("<slug>", slug).strip()
    if not path_text:
        return None
    path = Path(path_text)
    if path.is_absolute() or ".." in path.parts:
        return None
    if path.parts[:3] == ("docs", "status", slug) and len(path.parts) >= 5 and path.parts[3] == "roles":
        return None
    return ROOT / path


def materialized_status_artifact_body(intake: Intake, task: dict[str, object], artifact: Path, status_text: str) -> str:
    relative = rel(artifact)
    if relative.endswith("/evidence-report.md"):
        return f"""# Evidence Report

schema: ao-operator/evidence-report/v1
slug: {intake.slug}
source_task: {task["id"]}

AO Operator materialized this report from the provider STATUS block for
`{task["id"]}` after AO completed. The provider turn is intentionally
read-only; declared profile artifacts are reconstructed by the runner.

## Captured STATUS

```text
{status_text}
```
"""
    return f"""# AO Operator Materialized Artifact

schema: ao-operator/materialized-status-artifact/v1
slug: {intake.slug}
task: {task["id"]}
artifact: {relative}

## Captured STATUS

```text
{status_text}
```
"""


def materialize_declared_status_artifacts(
    paths: dict[str, Path],
    intake: Intake,
    event_text: str,
    tasks: list[dict[str, object]],
) -> list[Path]:
    """Write profile-declared non-role artifacts from captured STATUS blocks.

    AO provider turns for read-only profiles return STATUS text rather than
    mutating the repository directly. Role artifacts are always reconstructed
    under run-artifacts/<slug>/roles; this function materializes any additional
    declared write paths so profile contracts can expose durable user-facing
    artifacts without giving providers direct write authority.
    """
    written: list[Path] = []
    for task in tasks:
        status_text = extract_agent_status(event_text, str(task["id"]))
        if not status_text:
            continue
        for raw_path in task.get("writes", []):
            artifact = _declared_materialized_artifact_path(raw_path, intake.slug)
            if artifact is None:
                continue
            write(artifact, materialized_status_artifact_body(intake, task, artifact, status_text))
            written.append(artifact)
    return written


def _portable_python() -> str:
    # F2 cross-platform: Windows hosts ship `python` / `py -3`, not `python3`.
    # Use the interpreter currently running this script (sys.executable),
    # honoring FACTORY_V3_PYTHON for explicit override (e.g. macOS callers
    # who want /opt/homebrew/bin/python3 instead of the system Python).
    override = os.environ.get("FACTORY_V3_PYTHON")
    return override if override else sys.executable


def run_local_validation(slug: str) -> list[str]:
    py = _portable_python()
    commands = [
        [
            py,
            "-m",
            "py_compile",
            "scripts/factory_run.py",
            "scripts/validate_factory.py",
            "scripts/factory_doctor.py",
            "scripts/render_runspec.py",
            "scripts/validate_scaffold.py",
        ],
        [py, "scripts/validate_scaffold.py"],
    ]
    evidence: list[str] = []
    for cmd in commands:
        result = run_command(cmd, ROOT, os.environ.copy(), timeout=180)
        evidence.append(f"`{command_text(cmd)}` exit={result.returncode}")
    return evidence


def run_factory_validation(slug: str, profile: str | None = None) -> str:
    cmd = [_portable_python(), "scripts/validate_factory.py", "--slug", slug]
    if profile and profile != "default":
        cmd.extend([
            "--profile",
            profile,
            "--skip-repo-checks",
            "--allow-untracked-artifacts",
            "--allow-missing-final-evaluation",
        ])
    result = run_command(cmd, ROOT, os.environ.copy(), timeout=180)
    return f"`{command_text(cmd)}` exit={result.returncode}"


def obligation_ledger_evidence(paths: dict[str, Path]) -> tuple[list[str], list[str]]:
    ledger_path = paths.get("obligation_ledger")
    if not ledger_path or not ledger_path.is_file():
        return [], ["Obligation ledger missing."]
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        checked = obligation_ledger.check_ledger(ledger, ROOT)
        obligation_ledger.write_ledger(ledger_path, checked)
    except Exception as exc:
        return [], [f"Obligation ledger check failed: {exc}"]

    summary = checked.get("summary") if isinstance(checked.get("summary"), dict) else {}
    verdict = str(checked.get("verdict") or "")
    fail = int(summary.get("fail") or 0)
    unverified = int(summary.get("unverified") or 0)
    evidence = [
        (
            f"Obligation ledger verdict={verdict} "
            f"pass={int(summary.get('pass') or 0)} fail={fail} "
            f"unverified={unverified} waived={int(summary.get('waived') or 0)} "
            f"path={rel(ledger_path)}"
        )
    ]
    blockers: list[str] = []
    if verdict != "accepted":
        blockers.append("Obligation ledger verdict was not accepted.")
    if fail:
        blockers.append(f"Obligation ledger has failed obligations: {fail}.")
    if unverified:
        blockers.append(f"Obligation ledger has unverified obligations: {unverified}.")
    return evidence, blockers


def contract_evidence(contract: Path | None) -> tuple[list[str], list[str]]:
    if not contract:
        return ["No Spec Forge contract configured for this run."], []
    contract_path = contract if contract.is_absolute() else ROOT / contract
    if not contract_path.is_file():
        return [], [f"Contract missing: {display_path(contract_path)}"]
    try:
        data = json.loads(contract_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [], [f"Contract JSON invalid: {exc}"]
    required = ["shalls", "acceptance_criteria", "sensitive_fields", "negative_constraints", "slices"]
    blockers = [f"Contract missing required field: {key}" for key in required if not data.get(key)]
    evidence = [f"Contract loaded: {display_path(contract_path)}"]
    for key in required:
        value = data.get(key)
        count = len(value) if isinstance(value, list) else (1 if value else 0)
        evidence.append(f"Contract {key}: {count}")
    return evidence, blockers


SUCCESS_RESULTS = {"DONE", "DONE_WITH_CONCERNS"}
FAILED_RESULTS = {"BLOCKED", "REJECTED"}
LOAD_BEARING_RESULT_TASKS = {"implementer-slice", "reviewer-slice", "integrator", "evaluator-closer"}


def runtime_role_results(tasks: list[dict[str, object]], role_bodies: list[str]) -> dict[str, str]:
    results: dict[str, str] = {}
    for index, body in enumerate(role_bodies):
        task_id = str(tasks[index]["id"]) if index < len(tasks) else ""
        heading = re.search(r"(?m)^#\s+(\S+)\s+Role Artifact\s*$", body)
        if heading:
            task_id = heading.group(1)
        match = re.search(r"\*{0,2}Result:\*{0,2}\s*([A-Z_]+)", body)
        if task_id and match:
            results[task_id] = match.group(1)
    return results


def slice_quorum_verdict(slice_results: list[str], num_slices: int) -> str:
    """Aggregate N slice results into a task-level verdict per SDD 07.

    Threshold = ceil(QUORUM_NUM * num_slices / QUORUM_DEN). Defaults to 3/4.
    Returns:
      DONE                — every slice is pure DONE
      DONE_WITH_CONCERNS  — at-or-above threshold, but at least one slice is
                            DONE_WITH_CONCERNS or BLOCKED
      BLOCKED             — below threshold

    Reuses module-level SUCCESS_RESULTS = {"DONE", "DONE_WITH_CONCERNS"}
    when counting how many slices succeeded; only pure DONE earns the
    pure-DONE verdict.
    """
    if num_slices <= 0 or factory_v3_config.QUORUM_DEN <= 0:
        return "BLOCKED"
    threshold = ceil(factory_v3_config.QUORUM_NUM * num_slices / factory_v3_config.QUORUM_DEN)
    done_count = sum(1 for r in slice_results if r in SUCCESS_RESULTS)
    if done_count < threshold:
        return "BLOCKED"
    if all(r == "DONE" for r in slice_results):
        return "DONE"
    return "DONE_WITH_CONCERNS"


def slice_role_results(role_results: dict[str, str]) -> dict[str, list[str]]:
    """Group slice results by role family.

    Returns a dict like:
      {"implementer-slice": ["DONE", "DONE", "BLOCKED"], "reviewer-slice": [...]}

    Only includes IDs that match `<role>-slice-<i>` (suffixed). Bare
    `implementer-slice` / `reviewer-slice` (N=1 case) are NOT included —
    they are handled by the existing per-task logic.
    """
    grouped: dict[str, list[str]] = {}
    for task_id, result in role_results.items():
        for prefix in ("implementer-slice-", "reviewer-slice-"):
            if task_id.startswith(prefix):
                family = prefix.rstrip("-")
                grouped.setdefault(family, []).append(result)
                break
    return grouped


def is_load_bearing_result_task(task_id: str) -> bool:
    return (
        task_id in LOAD_BEARING_RESULT_TASKS
        or _is_slice_implementer(task_id)
        or _is_slice_reviewer(task_id)
        or task_id.endswith("-factory")
        or task_id.endswith("-reviewer")
    )


def _slice_family(task_id: str) -> str:
    """Map a slice-suffixed task ID to its family bucket.

    Returns "implementer-slice" for "implementer-slice-N", "reviewer-slice"
    for "reviewer-slice-N", otherwise returns task_id unchanged. Bare N=1
    IDs ("implementer-slice", "reviewer-slice") map to themselves and are
    handled by the existing per-task logic.
    """
    if task_id.startswith("implementer-slice-"):
        return "implementer-slice"
    if task_id.startswith("reviewer-slice-"):
        return "reviewer-slice"
    return task_id


def aggregated_role_results(role_results: dict[str, str]) -> dict[str, str]:
    """Collapse slice-suffixed entries into family entries via quorum.

    For each slice family with N≥2 slice-suffixed entries, replaces the
    per-slice entries with a single family entry whose value is
    `slice_quorum_verdict(...)`. Non-slice IDs and bare N=1 slice IDs pass
    through unchanged.

    Used by runtime_blockers and runtime_concerns so that the ⌈3N/4⌉ quorum
    actually feeds the top-level decision.
    """
    grouped = slice_role_results(role_results)
    aggregated: dict[str, str] = {}
    for task_id, result in role_results.items():
        family = _slice_family(task_id)
        if family != task_id and family in grouped:
            continue
        aggregated[task_id] = result
    for family, results in grouped.items():
        aggregated[family] = slice_quorum_verdict(results, num_slices=len(results))
    return aggregated


def runtime_concerns(
    tasks: list[dict[str, object]],
    role_results: dict[str, str],
    patch_bundles: dict[str, dict[str, object]],
) -> list[str]:
    concerns: list[str] = []
    aggregated = aggregated_role_results(role_results)
    for family in ("implementer-slice", "reviewer-slice"):
        if aggregated.get(family) == "DONE_WITH_CONCERNS":
            failing = sorted(
                task_id
                for task_id, result in role_results.items()
                if _slice_family(task_id) == family and task_id != family and result != "DONE"
            )
            if failing:
                concerns.append(
                    f"{family} reached quorum with concerns; non-DONE slices: {', '.join(failing)}"
                )
    any_role_failed = any(result in FAILED_RESULTS for result in role_results.values())
    load_bearing_failed = any(
        result in FAILED_RESULTS
        for task_id, result in aggregated.items()
        if is_load_bearing_result_task(task_id)
    )
    if any_role_failed and not load_bearing_failed:
        concerns.append("At least one role returned BLOCKED or REJECTED.")
    for task in tasks:
        task_id = str(task["id"])
        if not is_mutator_task(task_id):
            continue
        bundle = patch_bundles.get(task_id)
        if (
            bundle
            and int(bundle.get("diff_bytes", 0)) <= 0
            and role_results.get(task_id) in SUCCESS_RESULTS
        ):
            concerns.append(f"{task_id} produced an empty patch bundle.")
    return concerns


def runtime_blockers(
    tasks: list[dict[str, object]],
    role_bodies: list[str],
    patch_bundles: dict[str, dict[str, object]],
    role_results: dict[str, str] | None = None,
) -> list[str]:
    role_results = role_results or runtime_role_results(tasks, role_bodies)
    aggregated = aggregated_role_results(role_results)
    blockers: list[str] = []
    if any(
        result in FAILED_RESULTS
        for task_id, result in aggregated.items()
        if is_load_bearing_result_task(task_id)
    ):
        blockers.append("At least one role returned BLOCKED or REJECTED.")
    if any("No agent STATUS text captured." in body for body in role_bodies):
        blockers.append("At least one role required STATUS fallback from AO completion evidence.")
    for task in tasks:
        task_id = str(task["id"])
        if not is_mutator_task(task_id):
            continue
        family = _slice_family(task_id)
        if family != task_id and aggregated.get(family) in SUCCESS_RESULTS:
            continue
        bundle = patch_bundles.get(task_id)
        if not bundle:
            blockers.append(f"{task_id} did not produce a patch bundle.")
            continue
        if (
            int(bundle.get("diff_bytes", 0)) <= 0
            and role_results.get(task_id) not in SUCCESS_RESULTS
        ):
            blockers.append(f"{task_id} produced an empty patch bundle.")
        if not bundle.get("status_captured"):
            blockers.append(f"{task_id} did not produce a parseable STATUS block.")
    return blockers


def evaluation_body(
    intake: Intake,
    paths: dict[str, Path],
    tasks: list[dict[str, object]],
    verdict: str,
    ao_run: str,
    evidence: list[str],
    concerns: list[str],
    blockers: list[str],
) -> str:
    role_lines = [f"run-artifacts/{intake.slug}/roles/{task['id']}.md" for task in tasks]
    patch_lines = [
        f"run-artifacts/{intake.slug}/patches/{task['id']}.patch"
        for task in tasks
        if is_mutator_task(str(task["id"]))
    ]
    return f"""# {intake.slug} Evaluation

Verdict: {verdict}
Slug: {intake.slug}
AO Run: {ao_run}
Spec: docs/specs/{intake.slug}-spec.md
Plan: docs/plans/{intake.slug}-plan.md

## Role Artifacts

{bullet(role_lines)}

## Patch Bundles

{bullet(patch_lines or ["none"])}

Evidence:

{bullet(evidence)}

Concerns:

{bullet(concerns or ["none"])}

Blockers:

{bullet(blockers or ["none"])}
"""


def write_evaluation(
    paths: dict[str, Path],
    intake: Intake,
    tasks: list[dict[str, object]],
    verdict: str,
    ao_run: str,
    evidence: list[str],
    concerns: list[str] | None = None,
    blockers: list[str] | None = None,
) -> None:
    write(
        paths["evaluation"],
        evaluation_body(intake, paths, tasks, verdict, ao_run, evidence, concerns or [], blockers or []),
    )


def _artifact_paths_for_evidence_pack(paths: dict[str, Path]) -> dict[str, list[Path]]:
    artifacts: list[Path] = []
    for key in ("status", "evaluation", "events", "runspec", "spec", "plan", "obligation_ledger"):
        path = paths.get(key)
        if path and path.is_file():
            artifacts.append(path)
    for key in ("roles_dir", "patches_dir"):
        root = paths.get(key)
        if root and root.is_dir():
            artifacts.extend(sorted(path for path in root.rglob("*") if path.is_file()))
    return {"factory-run": artifacts}


def redact_evidence_pack_sources(paths: dict[str, Path]) -> None:
    import redact_strict_public_artifacts

    files: list[Path] = []
    for key in ("status", "evaluation", "events", "runspec", "spec", "plan", "obligation_ledger"):
        path = paths.get(key)
        if path and path.is_file():
            files.append(path)
    for key in ("roles_dir", "patches_dir"):
        root = paths.get(key)
        if root and root.is_dir():
            files.extend(sorted(path for path in root.rglob("*") if path.is_file()))
    for path in files:
        if path.suffix not in redact_strict_public_artifacts.TEXT_SUFFIXES:
            continue
        original = path.read_text(encoding="utf-8", errors="replace")
        redacted, _counts = redact_strict_public_artifacts.redact_text(original)
        if redacted != original:
            path.write_text(redacted, encoding="utf-8")


def _deterministic_command_allowed(command: list[str]) -> bool:
    if not command:
        return False
    executable = Path(command[0]).name.lower()
    return executable in {"python", "python3", Path(sys.executable).name.lower()}


def _resolved_deterministic_command(command: list[str]) -> list[str]:
    executable = Path(command[0]).name.lower()
    if executable in {"python", "python3", Path(sys.executable).name.lower()}:
        return [_portable_python(), *command[1:]]
    return command


def _safe_relative_output(raw_output: object) -> Path | None:
    output = Path(str(raw_output))
    if output.is_absolute() or ".." in output.parts:
        return None
    return output


def materialize_deterministic_replay_outputs(
    *,
    paths: dict[str, Path],
    tasks: list[dict[str, object]],
    timeout_seconds: float,
) -> dict[str, list[Path]]:
    """Execute deterministic replay commands into a slug-local artifact root.

    Provider turns may describe deterministic outputs, but evidence-pack replay
    needs byte-for-byte command output. Materializing those outputs here makes
    the pack self-contained without trusting provider-authored files.
    """
    status = paths.get("status")
    if not status:
        return {}
    replay_root = status.parent / "deterministic-replay"
    artifacts: dict[str, list[Path]] = {}
    for task in tasks:
        if task.get("deterministic") is not True:
            continue
        command = task.get("replay_command")
        outputs = task.get("replay_outputs")
        if not (
            isinstance(command, list)
            and all(isinstance(part, str) and part for part in command)
            and isinstance(outputs, list)
            and outputs
        ):
            continue
        command = [str(part) for part in command]
        if not _deterministic_command_allowed(command):
            continue
        task_id = str(task["id"])
        task_dir = replay_root / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            _resolved_deterministic_command(command),
            cwd=task_dir,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            continue
        for output in outputs:
            rel_output = _safe_relative_output(output)
            if rel_output is None:
                continue
            path = task_dir / rel_output
            if path.is_file():
                artifacts.setdefault(task_id, []).append(path)
    return artifacts


def _relativize_evidence_pack_report(value: object) -> object:
    if isinstance(value, dict):
        return {key: _relativize_evidence_pack_report(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_relativize_evidence_pack_report(item) for item in value]
    if isinstance(value, str):
        path = Path(value)
        if path.is_absolute():
            return rel(path)
    return value


def _event_records_for_evidence_pack(events_path: Path) -> list[dict[str, object]]:
    if not events_path.is_file():
        return []
    records: list[dict[str, object]] = []
    for index, line in enumerate(events_path.read_text(encoding="utf-8").splitlines()):
        ts = line.split(maxsplit=1)[0] if line else ""
        task_match = re.search(r"\btask=([^\s]+)", line)
        records.append(
            {
                "ts": ts or f"1970-01-01T00:00:{index:02d}+00:00",
                "trace_id": "",
                "span_id": f"{index:016x}"[-16:],
                "type": "factory.event_line",
                "task_id": task_match.group(1) if task_match else "factory-run",
                "attrs": {"line": line},
            }
        )
    return records


def _transcripts_for_evidence_pack(paths: dict[str, Path]) -> dict[str, list[dict[str, object]]]:
    transcripts: dict[str, list[dict[str, object]]] = {}
    roles_dir = paths.get("roles_dir")
    if roles_dir and roles_dir.is_dir():
        for role_path in sorted(roles_dir.glob("*.md")):
            transcripts[role_path.stem] = [
                {
                    "role": "assistant",
                    "content": role_path.read_text(encoding="utf-8"),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
            ]
    return transcripts


def write_live_evidence_pack(
    *,
    paths: dict[str, Path],
    intake: Intake,
    tasks: list[dict[str, object]],
    providers: dict[str, str],
    run_id: str,
    hmac_key_hex: str | None = None,
    ed25519_private_key: Path | None = None,
    execute_deterministic_replay: bool = False,
    deterministic_replay_timeout_seconds: float = 5.0,
    factory_version: str = "unknown",
    ao_runtime_version: str = "unknown",
) -> dict[str, object]:
    import evidence_pack_verify
    import evidence_pack_writer

    now = datetime.now(timezone.utc).isoformat()
    task_records = [
        evidence_pack_writer.TaskRecord(
            task_id=str(task["id"]),
            role=str(task.get("role") or task["id"]),
            status="completed",
            started_at=now,
            completed_at=now,
            deterministic=bool(task.get("deterministic", False)),
            replay_command=(
                [str(part) for part in task["replay_command"]]
                if isinstance(task.get("replay_command"), list)
                else None
            ),
            replay_outputs=(
                [str(output) for output in task["replay_outputs"]]
                if isinstance(task.get("replay_outputs"), list)
                else None
            ),
        )
        for task in tasks
    ]
    provider_records = [
        evidence_pack_writer.ProviderRecord(
            role=task_id,
            name=provider,
            version="unknown",
        )
        for task_id, provider in sorted(providers.items())
    ]
    redact_evidence_pack_sources(paths)
    artifact_paths = _artifact_paths_for_evidence_pack(paths)
    deterministic_artifacts = (
        materialize_deterministic_replay_outputs(
            paths=paths,
            tasks=tasks,
            timeout_seconds=deterministic_replay_timeout_seconds,
        )
        if execute_deterministic_replay
        else {}
    )
    all_artifacts = artifact_paths.get("factory-run", [])
    for task in tasks:
        replay_outputs = task.get("replay_outputs")
        if not isinstance(replay_outputs, list):
            continue
        matched: list[Path] = []
        for output in replay_outputs:
            output_name = Path(str(output)).name
            matched.extend(path for path in all_artifacts if path.name == output_name)
            matched.extend(
                path
                for path in deterministic_artifacts.get(str(task["id"]), [])
                if path.name == output_name
            )
        if matched:
            artifact_paths[str(task["id"])] = sorted(set(matched))
    inputs = evidence_pack_writer.RunInputs(
        run_id=run_id,
        factory_version=factory_version,
        ao_runtime_version=ao_runtime_version,
        created_at=now,
        completed_at=now,
        operator=evidence_pack_writer.OperatorRecord(
            host_fingerprint="sha256:" + evidence_pack_writer._sha256_bytes(platform.node().encode("utf-8")),
            user_label=platform.node(),
        ),
        profile=evidence_pack_writer.ProfileRecord(
            name=str(_active_profile().get("profile")) if _active_profile() else "default",
            version="v1",
            policy_digest="sha256:" + evidence_pack_writer._sha256_bytes(
                (paths.get("policy").read_bytes() if paths.get("policy") and paths["policy"].is_file() else b"")
            ),
        ),
        providers=provider_records,
        tasks=task_records,
        events=_event_records_for_evidence_pack(paths["events"]),
        transcripts=_transcripts_for_evidence_pack(paths),
        artifact_paths=artifact_paths,
    )
    signer, hmac_key = evidence_pack_writer.signer_from_options(
        hmac_key_hex=hmac_key_hex,
        ed25519_private_key=ed25519_private_key,
    )
    output_dir = paths.get("evidence_packs_dir", paths["status"].parent / "evidence-packs")
    pack_dir = evidence_pack_writer.write_pack(inputs, output_dir, signer)
    archive = evidence_pack_writer.write_tar_zst(pack_dir, output_dir)
    verify = evidence_pack_verify.verify_pack(archive, hmac_key=hmac_key)
    replay = evidence_pack_verify.replay_pack(
        archive,
        hmac_key=hmac_key,
        execute_deterministic=execute_deterministic_replay,
        deterministic_timeout_seconds=deterministic_replay_timeout_seconds,
    )
    report = {
        "schema": "ao-operator/evidence-pack-live-run/v1",
        "run_id": run_id,
        "pack": rel(pack_dir),
        "archive": rel(archive),
        "signature_algo": signer.algo,
        "verify": _relativize_evidence_pack_report(verify),
        "replay": _relativize_evidence_pack_report(replay),
        "verdict": "PASS" if verify["verdict"] == "PASS" and replay["verdict"] == "PASS" else "FAIL",
    }
    summary = output_dir / f"evidence-pack-{run_id}-summary.json"
    write_json(summary, report)
    report["summary"] = str(summary)
    return report


def _remote_coordinator_url(env: dict[str, str]) -> str:
    return env.get("FACTORY_V3_REMOTE_COORDINATOR_URL", "").strip()


def _remote_node_for_host_tags(host_tags: list[str], env: dict[str, str]) -> str:
    if not host_tags:
        return env.get("FACTORY_V3_REMOTE_DEFAULT_NODE", "").strip() or "ubuntu-live-worker"
    key = "_".join(
        part
        for part in (
            re.sub(r"[^A-Za-z0-9]+", "_", tag).strip("_").upper()
            for tag in host_tags
        )
        if part
    )
    for prefix in ("FACTORY_V3_REMOTE_NODE_FOR_TAGS_", "FACTORY_V3_REMOTE_NODE_FOR_"):
        node_id = env.get(prefix + key, "").strip()
        if node_id:
            return node_id
    return {"mac,live": "mac-live-worker", "ubuntu": "ubuntu-live-worker"}.get(",".join(host_tags), "")


def _codex_sandbox_for_task(task: dict[str, object]) -> str:
    sandbox = str(task.get("codex_sandbox") or "workspace-write")
    if sandbox not in {"workspace-write", "danger-full-access"}:
        raise ValueError(f"unsupported codex_sandbox for {task.get('id')}: {sandbox!r}")
    return sandbox


def _codex_manifest_with_sandbox(manifest_body: str, sandbox: str) -> str:
    lines = manifest_body.splitlines()
    for idx, line in enumerate(lines[:-1]):
        if line.strip() == "- --sandbox":
            indent = line[: len(line) - len(line.lstrip())]
            lines[idx + 1] = f"{indent}- {sandbox}"
            return "\n".join(lines) + "\n"
    raise ValueError("codex agent manifest does not declare --sandbox")


def _remote_shell_evidence_instruction(host_tags: list[str]) -> str:
    if "windows" in host_tags:
        return (
            "When shell access is available on native Windows, include sanitized PowerShell evidence: "
            "`[System.Environment]::OSVersion.VersionString` returned text, without hostnames, usernames, "
            "private paths, or IP addresses. Do not run `uname` on Windows."
        )
    return (
        "When shell access is available, include sanitized OS evidence from the worker, "
        "but do not include hostnames, usernames, private paths, or IP addresses."
    )


def _runtime_capture_workspace_label(task: dict[str, object]) -> str:
    """Return a non-sensitive workspace label for generated role artifacts."""
    workspace = str(task.get("workspace", "")).strip()
    if not workspace or workspace == ".":
        return "${FACTORY_V3_ROOT}"
    if re.match(r"^[A-Za-z]:[\\/]", workspace):
        return "${FACTORY_V3_ROOT}"
    if workspace.startswith(("/", "\\")):
        return "${FACTORY_V3_ROOT}"
    path = Path(workspace)
    if path.is_absolute():
        return "${FACTORY_V3_ROOT}"
    if ".." in path.parts:
        return "<redacted-workspace>"
    return workspace


def _dispatch_chain_remote(
    ao_bin: str,
    ao_home: Path,
    env: dict[str, str],
    paths: dict[str, Path],
    intake: Intake,
    tasks: list[dict[str, object]],
    contract: Path | None,
    runspec_path: Path | None = None,
    events_path: Path | None = None,
) -> dict[str, object]:
    def bridge_binary() -> Path:
        override = env.get("FACTORY_V3_REMOTE_CODEX_FLOW_BIN", "").strip()
        if override:
            path = Path(override)
            if path.is_file():
                return path
            raise FileNotFoundError(f"FACTORY_V3_REMOTE_CODEX_FLOW_BIN not found: {override}")
        ao_path = Path(ao_bin).resolve()
        for candidate in (
            ao_path.parent / "examples" / "remote_codex_smoke_flow",
            AO_RUNTIME_DEFAULT / "target" / "release" / "examples" / "remote_codex_smoke_flow",
            AO_RUNTIME_DEFAULT / "target" / "debug" / "examples" / "remote_codex_smoke_flow",
        ):
            if candidate.is_file():
                return candidate
        raise FileNotFoundError("remote_codex_smoke_flow example not found")

    def key_file(tmp_dir: Path, name: str, default_hex: str) -> Path:
        override = env.get(name, "").strip()
        if override:
            path = Path(override)
            if path.is_file():
                return path
            raise FileNotFoundError(f"{name} not found: {override}")
        path = tmp_dir / f"{name.lower()}.hex"
        path.write_text(default_hex + "\n", encoding="utf-8")
        return path

    def declared_write(task: dict[str, object]) -> str:
        for raw in task.get("writes", []):
            item = str(raw).replace("<slug>", intake.slug).strip()
            if item and not Path(item).is_absolute() and item != ".":
                return item
        return f"run-artifacts/{intake.slug}/roles/{task['id']}.md"

    def prepare_workspace(task_dir: Path, task: dict[str, object]) -> Path:
        workspace = task_dir / "workspace"
        (workspace / ".codex" / "agents").mkdir(parents=True, exist_ok=True)
        (workspace / "config" / "policy").mkdir(parents=True, exist_ok=True)
        manifest_source = ROOT / ".codex" / "agents" / "codex-default.yaml"
        manifest_target = workspace / ".codex" / "agents" / "codex-default.yaml"
        sandbox = _codex_sandbox_for_task(task)
        manifest_body = manifest_source.read_text(encoding="utf-8")
        if sandbox != "workspace-write":
            manifest_body = _codex_manifest_with_sandbox(manifest_body, sandbox)
        manifest_target.write_text(manifest_body, encoding="utf-8")
        shutil.copy2(ROOT / "ao" / "policy" / "local-dev.yaml", workspace / "config" / "policy" / "local-dev.yaml")
        return workspace

    def prior_context(task: dict[str, object]) -> str:
        parts: list[str] = []
        for dep in [str(dep) for dep in task.get("deps", [])]:
            path = ROOT / "run-artifacts" / intake.slug / "roles" / f"{dep}.md"
            if path.is_file():
                parts.append(fenced(path, read_for_prompt(path)))
        return "\n\n## Remote Dispatch Prior Role Artifacts\n\n" + "\n\n".join(parts) if parts else ""

    def event_line(kind: str, task_id: str, payload_json: str, timestamp: str | None = None) -> str:
        return f"{timestamp or datetime.now(timezone.utc).isoformat()}  {kind:<28} task={task_id:<28} {payload_json}"

    def status_from_artifacts(artifacts: list[dict[str, object]]) -> str:
        for artifact in artifacts:
            text = artifact.get("contentsUtf8")
            if isinstance(text, str):
                found = status_block(text)
                if found:
                    return found
        return ""

    def write_remote_artifacts(summary: dict[str, object]) -> list[str]:
        written: list[str] = []
        artifacts = summary.get("artifacts")
        if not isinstance(artifacts, list):
            return written
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            name = artifact.get("name")
            contents = artifact.get("contentsUtf8")
            if not isinstance(name, str) or not isinstance(contents, str):
                continue
            path = ROOT / name
            write(path, contents)
            written.append(rel(path))
        return written

    def summary_events(task: dict[str, object], run_id: str, node_id: str, output: str, summary: dict[str, object]) -> str:
        task_id = str(task["id"])
        lines: list[str] = []
        raw_events = summary.get("events")
        if isinstance(raw_events, list):
            for raw in raw_events:
                if isinstance(raw, dict):
                    lines.append(
                        event_line(
                            str(raw.get("kind") or ""),
                            task_id,
                            str(raw.get("payloadJson") or "{}"),
                            str(raw.get("timestamp") or datetime.now(timezone.utc).isoformat()),
                        )
                    )
        artifacts = [item for item in summary.get("artifacts", []) if isinstance(item, dict)]
        status_text = status_from_artifacts(artifacts)
        if not status_text and summary.get("finalStatus") == "completed":
            status_text = (
                "Result: DONE\n"
                f"Artifact: {output}\n"
                "Evidence:\n"
                f"- AO coordinator run {run_id} dispatched task {task_id} to node {node_id}.\n"
                f"- Artifact streamed back from {output}.\n"
                "Concerns:\n- none\n"
                "Blocker: none"
            )
        if status_text:
            lines.append(event_line("agent.stdout", task_id, json.dumps({"line": status_text})))
        return "\n".join(lines)

    def ordered_tasks() -> list[dict[str, object]]:
        remaining = {str(task["id"]): task for task in tasks}
        ordered: list[dict[str, object]] = []
        completed: set[str] = set()
        while remaining:
            ready = [tid for tid, task in remaining.items() if all(str(dep) in completed for dep in task.get("deps", []))]
            if not ready:
                raise ValueError("remote dispatch task graph has a dependency cycle or missing dependency")
            for tid in ready:
                ordered.append(remaining.pop(tid))
                completed.add(tid)
        return ordered

    runspec = runspec_path if runspec_path is not None else paths["runspec"]
    events = events_path if events_path is not None else paths["events"]
    coordinator_url = _remote_coordinator_url(env)
    enrollment = Path(env.get("FACTORY_V3_REMOTE_ENROLLMENT", "").strip() or ao_home / "node-enrollment.yaml")
    if not enrollment.is_file():
        raise FileNotFoundError(f"remote enrollment file not found: {enrollment}")

    run_id = f"r-{intake.slug}-remote-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    stdout_lines = [f"ok run {run_id} remote coordinator dispatch started"]
    stderr_lines: list[str] = []
    event_chunks: list[str] = []
    returncode = 0

    with tempfile.TemporaryDirectory(prefix="ao-operator-remote-") as tmp:
        tmp_dir = Path(tmp)
        signing_key = key_file(tmp_dir, "FACTORY_V3_REMOTE_SIGNING_KEY", "0b" * 32)
        verify_key = key_file(tmp_dir, "FACTORY_V3_REMOTE_VERIFY_KEY", "0c" * 32)
        bridge = bridge_binary()
        for task in ordered_tasks():
            task_id = str(task["id"])
            host_tags = [str(tag) for tag in task.get("host_tag", []) if str(tag)]
            node_id = _remote_node_for_host_tags(host_tags, env)
            if not node_id:
                returncode = 1
                event_chunks.append(event_line("task.failed", task_id, json.dumps({"reason": "missing-node-mapping", "hostTags": host_tags})))
                stderr_lines.append(f"{task_id}: no remote node mapping for host_tags={host_tags}")
                continue
            prompt_file = Path(str(task.get("promptFile") or paths["prompts_dir"] / f"{task_id}.md"))
            if not prompt_file.is_absolute():
                prompt_file = ROOT / prompt_file
            base_prompt = prompt_file.read_text(encoding="utf-8")
            provider = re.search(r"(?m)^Provider:\s*([A-Za-z0-9_-]+)\s*$", base_prompt)
            if provider and provider.group(1) != "codex":
                returncode = 1
                event_chunks.append(event_line("task.failed", task_id, json.dumps({"reason": "unsupported-remote-provider", "provider": provider.group(1)})))
                stderr_lines.append(f"{task_id}: remote bridge supports codex provider only, got {provider.group(1)}")
                continue
            task_dir = tmp_dir / task_id
            workspace = prepare_workspace(task_dir, task)
            output = declared_write(task)
            shell_instruction = _remote_shell_evidence_instruction(host_tags)
            remote_prompt = (
                f"declared_output: {output}\n\n"
                f"Create or modify exactly one file: {output}\n\n"
                "This AO Operator remote turn is running through the AO coordinator on a host-tagged worker. "
                "Write the declared output path inside this remote workspace before returning the required STATUS block. "
                f"{shell_instruction}\n\n"
                + base_prompt
                + prior_context(task)
            )
            prompt_path = task_dir / "prompt.md"
            prompt_path.write_text(remote_prompt, encoding="utf-8")
            cmd = [
                str(bridge),
                "--enrollment",
                str(enrollment),
                "--coordinator-url",
                coordinator_url,
                "--node-id",
                node_id,
                "--run-id",
                run_id,
                "--task-id",
                f"{run_id}-{task_id}",
                "--event-timeout-secs",
                env.get("FACTORY_V3_REMOTE_EVENT_TIMEOUT_SECS", "600"),
                "--skip-register",
                "--workspace",
                str(workspace),
                "--signing-key",
                str(signing_key),
                "--verify-key",
                str(verify_key),
                "--prompt-file",
                str(prompt_path),
            ]
            for tag in host_tags:
                cmd.extend(["--host-tag", tag])
            proc = run_command(cmd, ROOT, env, timeout=1800)
            if proc.returncode != 0:
                returncode = proc.returncode
                event_chunks.append(event_line("task.failed", task_id, json.dumps({"reason": "remote-bridge-error", "exit": proc.returncode})))
                stderr_lines.append(proc.stderr.strip() or proc.stdout.strip())
                break
            try:
                summary = json.loads(proc.stdout)
            except json.JSONDecodeError as exc:
                returncode = 1
                event_chunks.append(event_line("task.failed", task_id, json.dumps({"reason": "remote-bridge-invalid-json"})))
                stderr_lines.append(f"{task_id}: remote bridge emitted invalid JSON: {exc}")
                break
            if not isinstance(summary, dict):
                returncode = 1
                break
            written = write_remote_artifacts(summary)
            event_chunks.append(summary_events(task, run_id, node_id, output, summary))
            stdout_lines.append(f"{task_id}: node={node_id} tags={','.join(host_tags)} finalStatus={summary.get('finalStatus')} artifacts={','.join(written) or 'none'}")
            if summary.get("finalStatus") != "completed":
                returncode = 1
                break

    if returncode == 0:
        stdout_lines.append(f"ok run {run_id} remote coordinator dispatch completed")
    event_chunks.append(event_line("run.completed" if returncode == 0 else "run.failed", "run", json.dumps({"run_id": run_id, "runspec": rel(runspec)})))
    event_text_raw = "\n".join(chunk for chunk in event_chunks if chunk)
    run_result = subprocess.CompletedProcess([ao_bin, "run", str(runspec), "--remote-coordinator", coordinator_url], returncode, "\n".join(stdout_lines), "\n".join(stderr_lines))
    events_result = subprocess.CompletedProcess([ao_bin, "run", run_id, "events"], 0, event_text_raw, "")
    event_text = write_events(events, run_id, run_result, events_result)
    patch_bundles = write_patch_bundles(paths, intake, tasks, event_text)
    role_paths = write_role_artifacts(paths, intake, event_text, run_id, tasks, patch_bundles)
    materialize_declared_status_artifacts(paths, intake, event_text, tasks)
    validation_evidence = run_local_validation(intake.slug)
    contract_validation_evidence, contract_blockers = contract_evidence(contract)
    ao_completed = run_result.returncode == 0 and "run.completed" in event_text
    roles_exist = all(path.is_file() for path in role_paths)
    role_bodies = [path.read_text(encoding="utf-8") for path in role_paths if path.is_file()]
    blockers: list[str] = []
    if not ao_completed:
        blockers.append("AO remote coordinator run did not complete.")
    if not roles_exist:
        blockers.append("One or more role artifacts are missing.")
    role_results = runtime_role_results(tasks, role_bodies)
    concerns = runtime_concerns(tasks, role_results, patch_bundles)
    blockers.extend(runtime_blockers(tasks, role_bodies, patch_bundles, role_results))
    return {
        "run_result": run_result,
        "run_id": run_id,
        "event_text": event_text,
        "patch_bundles": patch_bundles,
        "role_paths": role_paths,
        "role_bodies": role_bodies,
        "role_results": role_results,
        "validation_evidence": validation_evidence,
        "contract_validation_evidence": contract_validation_evidence,
        "contract_blockers": contract_blockers,
        "ao_completed": ao_completed,
        "roles_exist": roles_exist,
        "blockers": blockers,
        "concerns": concerns,
    }


def _dispatch_chain(
    ao_bin: Path,
    ao_home: Path,
    env: dict[str, str],
    paths: dict[str, Path],
    intake: Intake,
    tasks: list[dict[str, object]],
    contract: Path | None,
    runspec_path: Path | None = None,
    events_path: Path | None = None,
) -> dict[str, object]:
    """Run a single AO dispatch and capture per-chain results.

    Returns a dict with keys:
      - run_result, run_id, event_text
      - patch_bundles, role_paths, role_bodies, role_results
      - validation_evidence, contract_validation_evidence, contract_blockers
      - ao_completed, roles_exist
      - blockers (chain-level: AO-incomplete, missing-roles, runtime_blockers)
      - concerns (runtime_concerns)

    Used by run_live for both the N=1 single-chain case and the N>=2
    split-dispatch case (Phase 1.5).

    runspec_path / events_path override paths["runspec"] / paths["events"]
    respectively; used in N>=2 mode so each chain writes its own files.
    """
    if _active_remote() and _remote_coordinator_url(env):
        return _dispatch_chain_remote(
            str(ao_bin),
            ao_home,
            env,
            paths,
            intake,
            tasks,
            contract,
            runspec_path=runspec_path,
            events_path=events_path,
        )

    runspec = runspec_path if runspec_path is not None else paths["runspec"]
    events = events_path if events_path is not None else paths["events"]
    run_result = run_command([ao_bin, "run", str(runspec)], ROOT, env)
    run_id = extract_run_id(run_result.stdout + "\n" + run_result.stderr)
    events_result = collect_events(ao_bin, ao_home, run_id)
    event_text = write_events(events, run_id, run_result, events_result)
    patch_bundles = write_patch_bundles(paths, intake, tasks, event_text)
    role_paths = write_role_artifacts(paths, intake, event_text, run_id, tasks, patch_bundles)
    materialize_declared_status_artifacts(paths, intake, event_text, tasks)
    validation_evidence = run_local_validation(intake.slug)
    contract_validation_evidence, contract_blockers = contract_evidence(contract)

    ao_completed = run_result.returncode == 0 and (
        "completed" in run_result.stdout.lower() or "run.completed" in event_text
    )
    roles_exist = all(path.is_file() for path in role_paths)
    role_bodies = [path.read_text(encoding="utf-8") for path in role_paths if path.is_file()]
    blockers: list[str] = []
    if not ao_completed:
        blockers.append("AO run did not complete.")
    if not roles_exist:
        blockers.append("One or more role artifacts are missing.")
    role_results = runtime_role_results(tasks, role_bodies)
    concerns = runtime_concerns(tasks, role_results, patch_bundles)
    blockers.extend(runtime_blockers(tasks, role_bodies, patch_bundles, role_results))

    return {
        "run_result": run_result,
        "run_id": run_id,
        "event_text": event_text,
        "patch_bundles": patch_bundles,
        "role_paths": role_paths,
        "role_bodies": role_bodies,
        "role_results": role_results,
        "validation_evidence": validation_evidence,
        "contract_validation_evidence": contract_validation_evidence,
        "contract_blockers": contract_blockers,
        "ao_completed": ao_completed,
        "roles_exist": roles_exist,
        "blockers": blockers,
        "concerns": concerns,
    }


def run_live(
    intake: Intake,
    providers: dict[str, str],
    paths: dict[str, Path],
    ao_home: Path,
    tasks: list[dict[str, object]],
    topology: Path | None,
    contract: Path | None,
    workspace_root: Path | None = None,
    evidence_hmac_key_hex: str | None = None,
    evidence_ed25519_private_key: Path | None = None,
    execute_deterministic_replay: bool = False,
    deterministic_replay_timeout_seconds: float = 5.0,
) -> int:
    if intake.blocked:
        write_evaluation(
            paths,
            intake,
            tasks,
            "REJECTED",
            "not-dispatched",
            ["Shape gate evaluated before AO dispatch."],
            blockers=[intake.blocker],
        )
        write(paths["status"], status_body(intake, "run", providers, verdict="REJECTED", ao_run="not-dispatched", topology=topology, contract=contract))
        return 1

    try:
        ao_bin = ao_binary()
    except FileNotFoundError as exc:
        write_evaluation(paths, intake, tasks, "REJECTED", "not-dispatched", [], blockers=[str(exc)])
        return 3

    ensure_ao_home(ao_bin, ao_home)
    env = os.environ.copy()
    env["AO_HOME"] = str(ao_home)

    # Detect N>=2 mode from expanded slice IDs (Phase 1.5).
    # Match `implementer-slice-<digits>$` only — `expand_slice_topology` always
    # emits numeric suffixes for N>=2 and leaves the bare `implementer-slice`
    # for N=1, so a digit-anchored check is robust against future custom
    # topology task ids that happen to share the prefix.
    is_split_mode = any(
        re.search(r"implementer-slice-\d+$", str(t["id"])) for t in tasks
    )

    if is_split_mode:
        workspace_root_for_runspec = workspace_root if workspace_root is not None else ROOT
        chain1_tasks, chain2_tasks = _split_topology_for_n_ge_2(tasks)
        chain1_runspec = paths["runspec"].with_name(f"{intake.slug}-chain1.runspec.yaml")
        chain1_events = paths["events"].with_name(f"{intake.slug}-chain1-ao-events.md")
        write(chain1_runspec, runspec_body(intake, providers, workspace_root_for_runspec, chain1_tasks))
        chain1 = _dispatch_chain(
            ao_bin, ao_home, env, paths, intake, chain1_tasks, contract,
            runspec_path=chain1_runspec, events_path=chain1_events,
        )

        slice_ids = [str(t["id"]) for t in chain1_tasks if str(t["id"]).startswith("implementer-slice-")]
        materialized, mat_notes, mat_blockers = materialize_integrator_workspace(
            slug=intake.slug,
            slice_ids=slice_ids,
            patches_dir=paths["patches_dir"],
            workspace_root=workspace_root_for_runspec,
        )

        if materialized is None:
            # Chain 2 cannot dispatch — bail with chain1 + materialize evidence
            run_result = chain1["run_result"]
            run_id = chain1["run_id"]
            patch_bundles = chain1["patch_bundles"]
            ao_completed = chain1["ao_completed"]
            roles_exist = chain1["roles_exist"]
            validation_evidence = chain1["validation_evidence"]
            contract_validation_evidence = chain1["contract_validation_evidence"]
            contract_blockers = chain1["contract_blockers"]
            concerns = list(chain1["concerns"])
            blockers = list(chain1["blockers"]) + mat_blockers
            materialized_path = None
            event_text = str(chain1["event_text"])
        else:
            # Bind chain-2 task workspaces to the materialized worktree.
            # task["workspace"] is the source of truth here: runspec_body
            # consults it first (line ~999), and several downstream readers
            # (status doc, role artifact body, validation paths) read the
            # same field. The runspec_body workspace arg below is therefore
            # only a fallback that should never fire for chain 2.
            for task in chain2_tasks:
                task["workspace"] = str(materialized)
            # Re-render chain-2 prompts AFTER chain-1 completes. The initial
            # materialize() pass wrote prompts using BASELINE tasks (no
            # chain1_handoffs), so without this re-render the chain-2
            # integrator/evaluator prompts have no Prior Role Handoff Content.
            # We re-render here (not earlier) because artifact_injections
            # reads role_dir / f"{dep}.md" — those files only exist after
            # chain-1 wrote its role artifacts.
            for task in chain2_tasks:
                write(paths["prompts_dir"] / f"{task['id']}.md", prompt_body(intake, task, providers, contract))
            chain2_runspec = paths["runspec"].with_name(f"{intake.slug}-chain2.runspec.yaml")
            chain2_events = paths["events"].with_name(f"{intake.slug}-chain2-ao-events.md")
            write(chain2_runspec, runspec_body(intake, providers, workspace_root_for_runspec, chain2_tasks))
            chain2 = _dispatch_chain(
                ao_bin, ao_home, env, paths, intake, chain2_tasks, contract,
                runspec_path=chain2_runspec, events_path=chain2_events,
            )
            # Merge: chain 2 owns the final verdict via integrator + evaluator-closer.
            # validation_evidence: chain 1 and chain 2 both call run_local_validation
            # on the same slug (idempotent, slug-scoped), so chain 2's result is
            # authoritative without dropping any signal.
            run_result = chain2["run_result"]
            run_id = chain2["run_id"]
            patch_bundles = {**chain1["patch_bundles"], **chain2["patch_bundles"]}
            ao_completed = chain1["ao_completed"] and chain2["ao_completed"]
            roles_exist = chain1["roles_exist"] and chain2["roles_exist"]
            validation_evidence = chain2["validation_evidence"]
            contract_validation_evidence = chain2["contract_validation_evidence"]
            contract_blockers = chain2["contract_blockers"]
            concerns = list(chain1["concerns"]) + list(chain2["concerns"])
            blockers = list(chain1["blockers"]) + list(chain2["blockers"]) + mat_blockers
            materialized_path = str(materialized)
            event_text = "\n".join([str(chain1["event_text"]), str(chain2["event_text"])])
    else:
        chain = _dispatch_chain(ao_bin, ao_home, env, paths, intake, tasks, contract)
        run_result = chain["run_result"]
        run_id = chain["run_id"]
        event_text = str(chain["event_text"])
        patch_bundles = chain["patch_bundles"]
        ao_completed = chain["ao_completed"]
        roles_exist = chain["roles_exist"]
        validation_evidence = chain["validation_evidence"]
        contract_validation_evidence = chain["contract_validation_evidence"]
        contract_blockers = chain["contract_blockers"]
        concerns = chain["concerns"]
        blockers = list(chain["blockers"])
        materialized_path = None

    blockers.extend(contract_blockers)
    obligation_evidence, obligation_blockers = obligation_ledger_evidence(paths)
    blockers.extend(obligation_blockers)
    environmental_scrubbed: list[str] = []
    if workspace_root is not None:
        environmental_scrubbed = scrub_claude_mem_pollution(workspace_root)
    evidence = [
        f"AO command exit={run_result.returncode}",
        f"AO run id={run_id}",
        f"AO completed={str(ao_completed).lower()}",
        f"Role artifacts exist={str(roles_exist).lower()}",
        f"Patch bundles captured={len(patch_bundles)}",
        f"AO events: {rel(paths['events'])}",
        *failure_diagnostics_evidence(event_text),
        *contract_validation_evidence,
        *validation_evidence,
        *obligation_evidence,
    ]
    if environmental_scrubbed:
        evidence.append("Workspace environmental scrubbed: " + ", ".join(environmental_scrubbed))
        concerns = list(concerns) + [
            "Provider-injected claude-mem context was scrubbed from the workspace root."
        ]
    active_profile = _active_profile()
    profile_name = str(active_profile.get("profile")) if isinstance(active_profile, dict) else None
    evidence.append(run_factory_validation(intake.slug, profile=profile_name))
    if evidence_hmac_key_hex or evidence_ed25519_private_key:
        try:
            pack_report = write_live_evidence_pack(
                paths=paths,
                intake=intake,
                tasks=tasks,
                providers=providers,
                run_id=run_id,
                hmac_key_hex=evidence_hmac_key_hex,
                ed25519_private_key=evidence_ed25519_private_key,
                execute_deterministic_replay=execute_deterministic_replay,
                deterministic_replay_timeout_seconds=deterministic_replay_timeout_seconds,
            )
        except Exception as exc:
            blockers.append(f"Evidence pack generation failed: {exc}")
        else:
            evidence.append(f"Evidence pack archive={rel(Path(str(pack_report['archive'])))}")
            evidence.append(f"Evidence pack replay verdict={pack_report['replay']['verdict']}")
            if pack_report["verdict"] != "PASS":
                blockers.append("Evidence pack replay verification failed.")
    evaluation_ready = not blockers
    verdict = "ACCEPTED" if evaluation_ready else "REJECTED"
    write_evaluation(paths, intake, tasks, verdict, run_id, evidence, concerns=concerns, blockers=blockers)
    write(paths["status"], status_body(intake, "run", providers, verdict=verdict, ao_run=run_id, topology=topology, contract=contract, materialized_workspace=materialized_path))
    return 0 if verdict == "ACCEPTED" else 1


SPEC_KIT_ALIASES = {"specify", "plan", "tasks", "analyze"}


def _default_slug_for_brief(brief: str) -> str:
    stem = Path(brief).stem
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return slug or "factory-run"


def _handle_spec_kit_alias(argv: list[str]) -> int | list[str]:
    if len(argv) < 2 or argv[1] not in SPEC_KIT_ALIASES:
        return argv
    command = argv[1]
    if command == "specify":
        if len(argv) < 3:
            print("factory_run.py specify: missing <brief>", file=sys.stderr)
            return 2
        brief = argv[2]
        rest = argv[3:]
        rewritten = [argv[0], "--brief", brief, "--profile", "greenfield", "--dry-run"]
        if "--slug" not in rest:
            rewritten.extend(["--slug", _default_slug_for_brief(brief)])
        rewritten.extend(rest)
        return rewritten

    parser = argparse.ArgumentParser(prog=f"{Path(argv[0]).name} {command}")
    parser.add_argument("slug")
    parser.add_argument("--profile", default="default")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv[2:])
    try:
        profile = _load_profile(args.profile)
    except (ProfileError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"factory_run.py {command}: profile load failed: {exc}", file=sys.stderr)
        return 2
    roles = _tasks_from_profile(profile)
    if command == "tasks":
        payload = {
            "schema": "ao-operator/spec-kit-alias/v1",
            "alias": command,
            "slug": args.slug,
            "profile": profile["profile"],
            "tasks": [{"id": role["id"], "deps": list(role.get("deps", []))} for role in roles],
        }
    elif command == "plan":
        planner = next((role for role in roles if role["id"] in {"planner", "planner-intake"}), roles[0])
        payload = {
            "schema": "ao-operator/spec-kit-alias/v1",
            "alias": command,
            "slug": args.slug,
            "profile": profile["profile"],
            "role": planner["id"],
            "writes": list(planner.get("writes", [])),
        }
    else:
        payload = {
            "schema": "ao-operator/spec-kit-alias/v1",
            "alias": command,
            "slug": args.slug,
            "profile": profile["profile"],
            "gates": {"gate_b": True, "gate_r": True},
            "inputs": [
                f"run-artifacts/{args.slug}/gate-b.json",
                f"docs/evaluations/{args.slug}-evaluation.md",
            ],
        }
    if args.json:
        handoff = _standalone_profile_handoff(str(profile["profile"]))
        if handoff is not None:
            payload["standalone_handoff"] = handoff
        print(json.dumps(payload, indent=2))
    elif command == "tasks":
        for task in payload["tasks"]:
            print(task["id"])
    else:
        print(json.dumps(payload, indent=2))
    return 0


def hermes_context_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog=f"{Path(sys.argv[0]).name} hermes-context")
    parser.add_argument("--slug", required=True, help="Factory status slug under run-artifacts/<slug>")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable Hermes context")
    args = parser.parse_args(argv)
    payload = hermes_context_payload(args.slug)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"schema={payload['schema']}")
        print(f"slug={payload['slug']}")
        print(f"status={payload['artifacts']['status']['path']}")
        print(f"runspec={payload['artifacts']['runspec']['path']}")
        print(f"evidence_pack_count={payload['artifacts']['evidence_packs']['count']}")
    return 0


def hermes_context_payload(slug: str) -> dict[str, object]:
    clean_slug = re.sub(r"[^A-Za-z0-9._-]+", "-", slug).strip("-")
    if not clean_slug:
        raise ValueError("slug must contain at least one safe path character")
    status_dir = ROOT / "run-artifacts" / clean_slug
    status_path = status_dir / f"{clean_slug}-status.md"
    runspec_path = status_dir / f"{clean_slug}.runspec.yaml"
    obligation_ledger_path = status_dir / "obligation-ledger.json"
    evidence_packs_dir = status_dir / "evidence-packs"
    evidence_packs = sorted(evidence_packs_dir.glob("*/evidence-pack.json")) if evidence_packs_dir.exists() else []
    tags = ["hermes", "ao-operator", "ao-operator", clean_slug]
    summary_body = (
        f"AO Operator status context for {clean_slug}. "
        f"Status exists={status_path.exists()}, RunSpec exists={runspec_path.exists()}, "
        f"obligation ledger exists={obligation_ledger_path.exists()}, "
        f"evidence packs={len(evidence_packs)}."
    )
    return {
        "schema": "ao-operator/hermes-context/v1",
        "slug": clean_slug,
        "status_dir": rel(status_dir),
        "artifacts": {
            "status": path_descriptor(status_path),
            "runspec": path_descriptor(runspec_path),
            "obligation_ledger": path_descriptor(obligation_ledger_path),
            "evidence_packs": {
                "dir": rel(evidence_packs_dir),
                "count": len(evidence_packs),
                "items": [path_descriptor(path) for path in evidence_packs],
            },
        },
        "memory": {
            "tags": tags,
            "recommended_records": [
                {
                    "kind": "factory-context",
                    "title": f"AO Operator context: {clean_slug}",
                    "body": summary_body,
                    "source_path": rel(status_path),
                }
            ],
            "ao2_write_command": [
                "ao2",
                "memory",
                "write",
                "--target",
                ".",
                "--kind",
                "factory-context",
                "--title",
                f"AO Operator context: {clean_slug}",
                "--body",
                summary_body,
                "--source-path",
                rel(status_path),
                *sum((["--tag", tag] for tag in tags), []),
                "--json",
            ],
        },
        "trust_boundary": {
            "hermes_role": "front_end_and_memory_reader",
            "factory_v3_role": "ao_operator_compatibility_layer",
            "ao2_role": "trusted_execution_memory_and_evidence_boundary",
        },
    }


def path_descriptor(path: Path) -> dict[str, object]:
    return {
        "path": rel(path),
        "exists": path.exists(),
        "bytes": path.stat().st_size if path.exists() and path.is_file() else 0,
    }


def main() -> int:
    alias_result = _handle_spec_kit_alias(sys.argv)
    if isinstance(alias_result, int):
        return alias_result
    if alias_result is not sys.argv:
        sys.argv = alias_result

    if len(sys.argv) > 1 and sys.argv[1] == "hermes-context":
        try:
            return hermes_context_main(sys.argv[2:])
        except ValueError as exc:
            print(f"factory_run.py hermes-context: {exc}", file=sys.stderr)
            return 2

    if len(sys.argv) > 1 and sys.argv[1] == "replay":
        import evidence_pack_verify

        return evidence_pack_verify.replay_main(sys.argv[2:])

    if len(sys.argv) > 1 and sys.argv[1] in {"enqueue", "pool", "run-once", "queue-status"}:
        import worker_pool

        command = "status" if sys.argv[1] == "queue-status" else sys.argv[1]
        return worker_pool.main([command, *sys.argv[2:]])

    parser = argparse.ArgumentParser(description="Run AO Operator")
    parser.add_argument("--brief", help="Task brief markdown")
    parser.add_argument("--slug", help="Stable artifact slug")
    parser.add_argument("--dry-run", action="store_true", help="Render artifacts without launching AO")
    parser.add_argument("--run", action="store_true", help="Render artifacts and launch AO")
    parser.add_argument("--render-only", action="store_true", help="Render all pre-AO artifacts without launching AO")
    parser.add_argument("--show-providers", action="store_true", help="Print resolved role provider mapping and exit")
    parser.add_argument("--provider-env", default=str(ROOT / ".env"), help="Provider .env file")
    parser.add_argument("--ao-home", help="AO home path; defaults to <tmpdir>/ao-operator-ao-<slug> where <tmpdir> is tempfile.gettempdir() (e.g. /tmp on POSIX, %%TEMP%% on Windows)")
    parser.add_argument("--workspace", default=".", help="Workspace path for AO tasks")
    parser.add_argument("--topology", help="Optional AO topology YAML to materialize instead of the baseline DAG")
    parser.add_argument("--contract", help="Optional Spec Forge contract JSON; defaults to contractFile found in topology")
    parser.add_argument(
        "--overwrite-artifacts",
        action="store_true",
        help="Allow replacing existing generated artifacts for the selected slug",
    )
    parser.add_argument(
        "--scrub-root-context",
        action="store_true",
        help="Strip provider-injected claude-mem blocks from Factory and workspace root instruction files before preflight",
    )
    parser.add_argument(
        "--profile",
        default="default",
        help="Role-chain profile name under profiles/<NAME>.json (default: 'default'). Use --list-profiles to see available profiles.",
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="List role-chain profiles under profiles/ and exit.",
    )
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Emit hostTags from per-role host_tag in the RunSpec for cross-host dispatch (v0.2 D2). Default off; the RunSpec is byte-for-byte unchanged in default mode.",
    )
    parser.add_argument(
        "--gate-b-strict",
        action="store_true",
        help="Write run-artifacts/<slug>/gate-b.json and fail before dispatch when intake/profile contract validation fails.",
    )
    parser.add_argument(
        "--gate-r-strict",
        action="store_true",
        help="Run Gate B plus post-run Gate R role artifact validation; fail closure when role artifacts drift from the Gate B contract.",
    )
    parser.add_argument(
        "--evidence-hmac-key-hex",
        default=os.environ.get("FACTORY_V3_EVIDENCE_HMAC_KEY_HEX", ""),
        help="When set, write and replay-verify a signed evidence pack after --run.",
    )
    parser.add_argument(
        "--evidence-ed25519-private-key",
        default=os.environ.get("FACTORY_V3_EVIDENCE_ED25519_PRIVATE_KEY", ""),
        help=(
            "When set, sign the post-run evidence pack with an Ed25519 PEM "
            "private key (requires optional cryptography)."
        ),
    )
    parser.add_argument(
        "--evidence-execute-deterministic",
        action="store_true",
        help=(
            "When writing a live evidence pack, execute deterministic non-LLM "
            "replay commands after signature/CAS verification."
        ),
    )
    parser.add_argument(
        "--evidence-deterministic-timeout-seconds",
        type=float,
        default=5.0,
        help="Timeout per deterministic evidence replay command when execution is enabled.",
    )
    args = parser.parse_args()
    if args.evidence_hmac_key_hex and args.evidence_ed25519_private_key:
        parser.error("--evidence-hmac-key-hex and --evidence-ed25519-private-key are mutually exclusive")
    _set_active_remote(bool(getattr(args, "remote", False)))

    if args.list_profiles:
        for entry in _list_profiles():
            print(f"{entry['name']}\t{entry['description']}")
        return 0

    if args.profile and args.profile != "default":
        try:
            profile = _load_profile(args.profile)
        except (ProfileError, FileNotFoundError, json.JSONDecodeError) as exc:
            print(f"factory_run.py: profile load failed: {exc}", file=sys.stderr)
            return 2
        _set_active_profile(profile)

    if args.show_providers:
        env = parse_env(Path(args.provider_env))
        active = _active_profile()
        tasks_for_show = _tasks_from_profile(active) if active is not None else BASELINE_TASKS
        try:
            providers = provider_map({**os.environ, **env}, tasks_for_show)
        except ValueError as exc:
            print(f"factory_run.py: {exc}", file=sys.stderr)
            return 2
        header = (
            f"ao-operator providers (profile={args.profile}):"
            if active is not None
            else "ao-operator providers:"
        )
        print(header)
        for task_id, provider in providers.items():
            print(f"  {task_id}: {provider}")
        return 0

    if not args.brief:
        parser.error("the following arguments are required: --brief")

    if sum([args.dry_run, args.run, args.render_only]) != 1:
        print("factory_run.py: choose exactly one of --dry-run, --run, or --render-only", file=sys.stderr)
        return 2
    if args.gate_r_strict and not args.run:
        print("factory_run.py: --gate-r-strict requires --run", file=sys.stderr)
        return 2
    if args.run:
        handoff_message = _standalone_profile_handoff_message(args.profile)
        if handoff_message:
            print(handoff_message, file=sys.stderr)
            return 2

    forbidden = reject_forbidden_env()
    if forbidden:
        print(f"factory_run.py: {forbidden}", file=sys.stderr)
        return 1

    brief_path = Path(args.brief)
    if not brief_path.is_absolute():
        brief_path = ROOT / brief_path
    if not brief_path.is_file():
        print(f"factory_run: error: --brief path does not exist: {args.brief}", file=sys.stderr)
        return 2

    if args.scrub_root_context:
        scrub_root_claude_mem_context(ROOT)

    env = parse_env(Path(args.provider_env))
    partition_slices: list[dict[str, object]] | None = None
    try:
        intake = make_intake(brief_path, args.slug)
        blockers = preflight_blockers(intake.slug, overwrite_artifacts=args.overwrite_artifacts)
        if blockers:
            for blocker in blockers:
                print(f"factory_run.py: preflight blocked: {blocker}", file=sys.stderr)
            return 1
        contract_path = Path(args.contract) if args.contract else None
        if args.topology and not contract_path:
            topology_text = (ROOT / args.topology if not Path(args.topology).is_absolute() else Path(args.topology)).read_text(encoding="utf-8")
            match = re.search(r"contractFile:\s*(\S+)", topology_text)
            if match:
                contract_path = Path(match.group(1))
        contract = load_contract(contract_path)
        topology_path = Path(args.topology) if args.topology else None
        active = _active_profile()
        if topology_path:
            tasks = parse_topology(topology_path, intake.slug, contract)
        elif active is not None:
            # Profile-derived chain (T4 SPEC F.1). Profiles encode their own
            # linear topology — slice fan-out is a default-chain concept tied
            # to implementer-slice / reviewer-slice, which non-default
            # profiles do not have.
            tasks = _tasks_from_profile(active)
        else:
            scoped = extract_scoped_writes(intake.brief)
            slices = auto_partition.partition(intake.brief, scoped)
            partition_slices = slices
            tasks = expand_slice_topology(BASELINE_TASKS, num_slices=len(slices), slice_specs=slices)
        run_blockers = live_run_blockers(tasks, run=args.run)
        if run_blockers:
            for blocker in run_blockers:
                print(f"factory_run.py: preflight blocked: {blocker}", file=sys.stderr)
            return 1
        providers = provider_map(env, tasks)
    except ValueError as exc:
        print(f"factory_run.py: {exc}", file=sys.stderr)
        return 2

    workspace_root = Path(args.workspace)
    if not workspace_root.is_absolute():
        workspace_root = ROOT / workspace_root
    workspace_root = workspace_root.absolute()
    if not (workspace_root / ".git").exists():
        print(f"factory_run: error: --workspace is not a git repository: {workspace_root}", file=sys.stderr)
        return 2
    if args.scrub_root_context and workspace_root.resolve() != ROOT.resolve():
        scrub_root_claude_mem_context(workspace_root)
    workspace_blocker = workspace_claude_mem_blocker(workspace_root)
    if workspace_blocker:
        print(f"factory_run.py: preflight blocked: {workspace_blocker}", file=sys.stderr)
        return 1

    prepare_worktrees(
        intake.slug,
        tasks,
        enabled=args.run or args.render_only,
        workspace_root=workspace_root,
    )
    if workspace_root.resolve() != ROOT.resolve():
        sync_agent_manifests_to(workspace_root)
    workspace = workspace_root
    mode = "dry-run" if args.dry_run else "render-only" if args.render_only else "materialized"
    paths = materialize(intake, providers, workspace, tasks, topology_path, contract_path, mode=mode)
    sync_generated_artifacts_to_workspace_root(paths, workspace_root, contract_path)
    sync_scoped_reads_to_workspace_root(intake, workspace_root)
    sync_factory_helper_scripts_to_workspace_root(workspace_root)
    sync_generated_artifacts_to_worktrees(paths, tasks, contract_path, workspace_root)
    sync_task_scoped_reads_to_worktrees(tasks, workspace_root, intake.slug)
    gate_b_report: dict[str, object] | None = None
    if args.gate_b_strict or args.gate_r_strict:
        gate_b_report = run_gate_b_strict(
            intake=intake,
            paths=paths,
            profile_name=args.profile,
            contract=contract_path,
            partition_slices=partition_slices,
        )
        if gate_b_report["verdict"] != "PASS":
            print_gate_errors("Gate B", gate_b_report)
            return 1
    if args.dry_run:
        print(json.dumps({"verdict": "DRY_RUN", "slug": intake.slug, "runspec": rel(paths["runspec"])}, indent=2))
        return 0
    if args.render_only:
        prompt_count = materialize_render_only_stubs(paths, tasks)
        write(paths["status"], status_body(intake, "render-only", providers, topology=topology_path, contract=contract_path))
        for note in cleanup_worktree_leases(intake.slug, workspace_root):
            print(note)
        print(f"factory_run: rendered slug={intake.slug} prompts={prompt_count} (no AO call)")
        return 0

    # Anchor each mutator worktree's HEAD at the post-sync state so that the
    # post-provider `git diff --cached` in git_diff() reflects only the
    # provider's edits (including newly-created files).
    snapshot_notes = snapshot_worktree_baselines(tasks, workspace_root)
    for note in snapshot_notes:
        print(note)
    ao_home = Path(args.ao_home) if args.ao_home else Path(tempfile.gettempdir()) / f"ao-operator-ao-{intake.slug}"
    run_rc = run_live(
        intake,
        providers,
        paths,
        ao_home,
        tasks,
        topology_path,
        contract_path,
        workspace_root=workspace,
        evidence_hmac_key_hex=args.evidence_hmac_key_hex or None,
        evidence_ed25519_private_key=(
            Path(args.evidence_ed25519_private_key)
            if args.evidence_ed25519_private_key
            else None
        ),
        execute_deterministic_replay=args.evidence_execute_deterministic,
        deterministic_replay_timeout_seconds=args.evidence_deterministic_timeout_seconds,
    )
    for note in cleanup_worktree_leases(intake.slug, workspace_root):
        print(note)
    if args.gate_r_strict:
        gate_r_report = run_gate_r_strict(intake=intake, paths=paths)
        if gate_r_report["verdict"] != "PASS":
            print_gate_errors("Gate R", gate_r_report)
            return 1
    return run_rc


if __name__ == "__main__":
    raise SystemExit(main())
