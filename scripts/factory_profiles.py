"""Factory profile loading, validation, projection, and policy rendering.

This module is deterministic configuration plumbing. It owns profile JSON
schema validation and projection into the task shape consumed by the runner;
it does not dispatch agents or make orchestration decisions.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILES_DIR = ROOT / "profiles"
PROFILE_SCHEMA_ID = "ao-operator/profile/v1"
PROFILE_VERSION = 1
_PROVIDER_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_TASK_FIELDS = (
    "id",
    "role",
    "provider_key",
    "deps",
    "reads",
    "writes",
    "host_tag",
    "codex_sandbox",
    "deterministic",
    "replay_command",
    "replay_outputs",
)


class ProfileError(ValueError):
    """Raised when a profile file fails schema validation."""


BASELINE_TASKS = [
    {
        "id": "planner-intake",
        "role": "Planner Intake",
        "provider_key": "FACTORY_V3_PLANNER_PROVIDER",
        "deps": [],
        "reads": ["task brief", "docs/sdd/"],
        "writes": ["docs/specs/<slug>-spec.md"],
    },
    {
        "id": "plan-hardener",
        "role": "Plan Hardener",
        "provider_key": "FACTORY_V3_PLAN_HARDENER_PROVIDER",
        "deps": ["planner-intake"],
        "reads": ["docs/specs/<slug>-spec.md", "docs/sdd/"],
        "writes": ["docs/plans/<slug>-plan.md"],
    },
    {
        "id": "factory-manager",
        "role": "Factory Manager",
        "provider_key": "FACTORY_V3_FACTORY_MANAGER_PROVIDER",
        "deps": ["plan-hardener"],
        "reads": ["docs/specs/<slug>-spec.md", "docs/plans/<slug>-plan.md"],
        "writes": ["run-artifacts/<slug>/<slug>-status.md"],
    },
    {
        "id": "implementer-slice",
        "role": "Implementer",
        "provider_key": "FACTORY_V3_IMPLEMENTER_PROVIDER",
        "deps": ["factory-manager"],
        "reads": ["docs/specs/<slug>-spec.md", "docs/plans/<slug>-plan.md"],
        "writes": ["scoped application artifacts from the accepted plan"],
    },
    {
        "id": "reviewer-slice",
        "role": "Slice Reviewer",
        "provider_key": "FACTORY_V3_SLICE_REVIEWER_PROVIDER",
        "deps": ["implementer-slice"],
        "reads": ["implementer artifact", "docs/specs/<slug>-spec.md"],
        "writes": ["run-artifacts/<slug>/roles/reviewer-slice.md"],
    },
    {
        "id": "integrator",
        "role": "Integrator",
        "provider_key": "FACTORY_V3_INTEGRATOR_PROVIDER",
        "deps": ["reviewer-slice"],
        "reads": ["accepted slice artifacts", "review artifact"],
        "writes": ["run-artifacts/<slug>/roles/integrator.md"],
    },
    {
        "id": "evaluator-closer",
        "role": "Evaluator Closer",
        "provider_key": "FACTORY_V3_EVALUATOR_CLOSER_PROVIDER",
        "deps": ["integrator"],
        "reads": ["spec", "plan", "AO events", "role artifacts"],
        "writes": ["docs/evaluations/<slug>-evaluation.md"],
    },
]


def validate_profile(name: str, raw: object) -> dict[str, object]:
    """Validate a parsed profile dict against ao-operator/profile/v1."""
    if not isinstance(raw, dict):
        raise ProfileError(f"profile {name!r}: top-level must be a JSON object")
    if raw.get("schema") != PROFILE_SCHEMA_ID:
        raise ProfileError(
            f"profile {name!r}: schema must be {PROFILE_SCHEMA_ID!r}, got {raw.get('schema')!r}"
        )
    if raw.get("version") != PROFILE_VERSION:
        raise ProfileError(
            f"profile {name!r}: version must be {PROFILE_VERSION}, got {raw.get('version')!r}"
        )
    if raw.get("profile") != name:
        raise ProfileError(
            f"profile {name!r}: top-level 'profile' field must equal filename stem, "
            f"got {raw.get('profile')!r}"
        )
    common_instructions = raw.get("common_instructions")
    if not isinstance(common_instructions, list) or not all(
        isinstance(s, str) for s in common_instructions
    ):
        raise ProfileError(f"profile {name!r}: common_instructions must be list[str]")
    roles = raw.get("roles")
    if not isinstance(roles, list) or not roles:
        raise ProfileError(f"profile {name!r}: roles must be a non-empty list")

    seen_ids: set[str] = set()
    for role in roles:
        if not isinstance(role, dict):
            raise ProfileError(f"profile {name!r}: each role must be a JSON object")
        rid = role.get("id")
        if not isinstance(rid, str) or not rid:
            raise ProfileError(f"profile {name!r}: role missing 'id' (str)")
        if rid in seen_ids:
            raise ProfileError(f"profile {name!r}: duplicate role id {rid!r}")
        seen_ids.add(rid)
        if not isinstance(role.get("role"), str):
            raise ProfileError(f"profile {name!r} role {rid!r}: 'role' must be str")
        provider_key = role.get("provider_key")
        if not isinstance(provider_key, str) or not _PROVIDER_KEY_RE.match(provider_key):
            raise ProfileError(
                f"profile {name!r} role {rid!r}: provider_key must match {_PROVIDER_KEY_RE.pattern!r}, "
                f"got {provider_key!r}"
            )
        for list_field in ("deps", "reads", "writes", "skills", "instructions"):
            value = role.get(list_field)
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ProfileError(
                    f"profile {name!r} role {rid!r}: {list_field} must be list[str]"
                )
        if "is_mutator" in role and not isinstance(role["is_mutator"], bool):
            raise ProfileError(
                f"profile {name!r} role {rid!r}: is_mutator must be bool when present"
            )
        if "deterministic" in role and not isinstance(role["deterministic"], bool):
            raise ProfileError(
                f"profile {name!r} role {rid!r}: deterministic must be bool when present"
            )
        if role.get("deterministic") is True:
            for field in ("replay_command", "replay_outputs"):
                value = role.get(field)
                if (
                    not isinstance(value, list)
                    or not value
                    or not all(isinstance(v, str) and v for v in value)
                ):
                    raise ProfileError(
                        f"profile {name!r} role {rid!r}: {field} must be non-empty list[str] "
                        "when deterministic is true"
                    )
        else:
            for field in ("replay_command", "replay_outputs"):
                if field in role:
                    value = role[field]
                    if not isinstance(value, list) or not all(
                        isinstance(v, str) and v for v in value
                    ):
                        raise ProfileError(
                            f"profile {name!r} role {rid!r}: {field} must be list[str] when present"
                        )
        if "host_tag" in role:
            host_tag = role["host_tag"]
            if (
                not isinstance(host_tag, list)
                or not all(isinstance(t, str) and t for t in host_tag)
            ):
                raise ProfileError(
                    f"profile {name!r} role {rid!r}: host_tag must be list[str] when present"
                )
        if "codex_sandbox" in role:
            sandbox = role["codex_sandbox"]
            if sandbox not in {"workspace-write", "danger-full-access"}:
                raise ProfileError(
                    f"profile {name!r} role {rid!r}: codex_sandbox must be "
                    "'workspace-write' or 'danger-full-access' when present"
                )

    for role in roles:
        for dep in role["deps"]:
            if dep not in seen_ids:
                raise ProfileError(
                    f"profile {name!r} role {role['id']!r}: dep {dep!r} not declared in this profile"
                )

    return {
        "profile": name,
        "schema": PROFILE_SCHEMA_ID,
        "version": PROFILE_VERSION,
        "description": str(raw.get("description", "")),
        "common_instructions": list(common_instructions),
        "policy_posture": raw.get("policy_posture"),
        "roles": list(roles),
        "roles_by_id": {role["id"]: role for role in roles},
    }


def load_profile(name: str, repo_root: Path | None = None) -> dict[str, object]:
    """Load profiles/<name>.json and return a validated, normalized dict."""
    base = (repo_root or ROOT) / "profiles"
    expected_name = name
    if ":" in name:
        namespace, profile_name = name.split(":", 1)
        if (
            not namespace
            or not profile_name
            or "/" in namespace
            or "\\" in namespace
            or "/" in profile_name
            or "\\" in profile_name
        ):
            raise FileNotFoundError(
                f"profile {name!r} is not a valid namespaced profile name"
            )
        path = base / namespace / f"{profile_name}.json"
    else:
        path = base / f"{name}.json"
    if not path.exists() and ":" not in name and "/" not in name and "\\" not in name:
        starter_path = base / "starters" / f"{name}.json"
        if starter_path.exists():
            path = starter_path
    if not path.exists():
        raise FileNotFoundError(
            f"profile {name!r} not found at {path}; run --list-profiles to see available profiles"
        )
    with path.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    return validate_profile(expected_name, raw)


def list_profiles(repo_root: Path | None = None) -> list[dict[str, str]]:
    """Return [{name, description}, ...] for every JSON in profiles/."""
    base = (repo_root or ROOT) / "profiles"
    if not base.is_dir():
        return []
    out: list[dict[str, str]] = []
    profile_paths = [
        *base.glob("*.json"),
        *(base / "starters").glob("*.json"),
        *(
            path
            for path in base.glob("*/*.json")
            if path.parent.name != "starters"
        ),
    ]
    for path in sorted(profile_paths):
        name = (
            path.stem
            if path.parent in (base, base / "starters")
            else f"{path.parent.name}:{path.stem}"
        )
        try:
            profile = load_profile(name, repo_root)
        except (ProfileError, FileNotFoundError, json.JSONDecodeError) as exc:
            out.append({"name": name, "description": f"<load error: {exc}>"})
            continue
        out.append({"name": name, "description": str(profile.get("description", ""))})
    return out


def tasks_from_profile(profile: dict[str, object]) -> list[dict[str, object]]:
    """Project a profile's role list into the runner task-dict shape."""
    raw_roles = profile.get("roles") or []
    tasks: list[dict[str, object]] = []
    for role in raw_roles:
        if not isinstance(role, dict):
            continue
        tasks.append({field: role[field] for field in _TASK_FIELDS if field in role})
    return tasks


def _q(value: str) -> str:
    """Quote a YAML scalar so it round-trips literally regardless of content."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_policy_yaml(profile: dict[str, object], slug: str) -> str:
    """Translate profile['policy_posture'] into an AO policy YAML body."""
    posture = profile.get("policy_posture") or {}
    profile_id = profile.get("profile") or "profile"
    rules: list[str] = []

    def emit(match_lines: list[str], decision: str, reason: str) -> None:
        rules.append("  - match:")
        rules.extend(f"      {line}" for line in match_lines)
        rules.append(f"    decision: {decision}")
        rules.append(f"    reason: {_q(reason)}")

    emit(["action.type: git.force_push"], "deny", "force-push is forbidden")
    emit(
        ["action.type: shell.run", 'action.command: "rm -rf /"'],
        "deny",
        "destructive shell command",
    )

    shell = posture.get("shell") or {}
    for prefix in shell.get("deny_prefixes") or []:
        emit(
            ["action.type: shell.run", f"action.commandPrefix: {_q(str(prefix))}"],
            "deny",
            f"{profile_id} profile posture denies shell prefix {prefix!r}",
        )
    for prefix in shell.get("require_approval_for") or []:
        emit(
            ["action.type: shell.run", f"action.commandPrefix: {_q(str(prefix))}"],
            "ask",
            f"{profile_id} profile posture requires approval for shell prefix {prefix!r}",
        )
    for prefix in shell.get("allow_prefixes") or []:
        emit(
            ["action.type: shell.run", f"action.commandPrefix: {_q(str(prefix))}"],
            "allow",
            f"{profile_id} profile posture allows shell prefix {prefix!r}",
        )

    network = posture.get("network") or {}
    if network.get("egress_default") == "deny" and not (network.get("allow_hosts") or []):
        emit(
            ["action.type: network.egress"],
            "deny",
            f"{profile_id} profile posture default-denies network egress (allow_hosts is empty)",
        )

    secrets = posture.get("secrets") or {}
    for key in secrets.get("forbidden_env") or []:
        emit(
            ["action.type: secrets.read", f"action.command: {_q(str(key))}"],
            "deny",
            f"{profile_id} profile posture forbids reading env secret {key!r}",
        )
    if secrets.get("require_approval_for_read"):
        emit(
            ["action.type: secrets.read"],
            "ask",
            f"{profile_id} profile posture requires approval for any secret read",
        )

    emit(
        ["action.type: agent.run.codex", "source.trust: local-user"],
        "allow",
        "local Codex CLI launch allowed for AO Operator smoke",
    )
    emit(
        ["action.type: agent.run.claude", "source.trust: local-user"],
        "allow",
        "local Claude Code CLI launch allowed for AO Operator smoke",
    )

    header = [
        f"id: ao-operator-{profile_id}-{slug}",
        "default_decision: allow",
        f'default_reason: "ao-operator {profile_id} profile posture: default-allow with explicit ordered deny/ask/allow rules"',
        "rules:",
    ]
    return "\n".join(header + rules) + "\n"


def profile_has_policy_posture(profile: dict[str, object] | None) -> bool:
    return (
        profile is not None
        and isinstance(profile.get("policy_posture"), dict)
        and bool(profile["policy_posture"])
    )
