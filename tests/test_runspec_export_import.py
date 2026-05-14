from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import runspec_export
import runspec_import


def test_round_trip_export_import_default_profile(tmp_path):
    payload = runspec_export.build_export(
        slug="bug-fix",
        profile_name="default",
        brief="examples/starters/bug-fix-example.md",
    )
    path = runspec_export.write_export(payload, runspec_export.target_path(tmp_path / "bug-fix"))

    imported = runspec_import.import_runspec(path)

    assert imported == payload


def test_malformed_yaml_rejected(tmp_path):
    path = tmp_path / "bad.factory" / "runspec.yaml"
    path.parent.mkdir()
    path.write_text("schema: [unterminated\n", encoding="utf-8")

    with pytest.raises(runspec_import.RunSpecImportError, match="malformed YAML"):
        runspec_import.import_runspec(path)


def test_schema_version_mismatch_rejected(tmp_path):
    payload = runspec_export.build_export(
        slug="bug-fix",
        profile_name="default",
        brief="examples/starters/bug-fix-example.md",
    )
    payload["schema"] = "ao-operator/runspec/v0"
    path = runspec_export.write_export(payload, runspec_export.target_path(tmp_path / "bug-fix"))

    with pytest.raises(runspec_import.RunSpecImportError, match="schema"):
        runspec_import.import_runspec(path)


def test_every_role_field_round_trips(tmp_path):
    payload = runspec_export.build_export(
        slug="evidence",
        profile_name="evidence",
        brief="examples/starters/smoke-test-example.md",
    )
    path = runspec_export.write_export(payload, runspec_export.target_path(tmp_path / "evidence"))
    imported = runspec_import.import_runspec(path)

    for exported, hydrated in zip(payload["roles"], imported["roles"], strict=True):
        assert set(hydrated) == {"id", "provider_key", "host_tag", "deps", "reads", "writes"}
        assert hydrated == exported


def test_unknown_dep_rejected(tmp_path):
    payload = runspec_export.build_export(
        slug="bug-fix",
        profile_name="default",
        brief="examples/starters/bug-fix-example.md",
    )
    payload["roles"][0]["deps"] = ["missing"]
    path = runspec_export.write_export(payload, runspec_export.target_path(tmp_path / "bug-fix"))

    with pytest.raises(runspec_import.RunSpecImportError, match="unknown dep"):
        runspec_import.import_runspec(path)


def test_cli_export_path_shape(tmp_path):
    out = runspec_export.target_path(tmp_path / "bug-fix")

    assert out == tmp_path / "bug-fix.factory" / "runspec.yaml"
