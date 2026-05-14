from __future__ import annotations

import sbom_python


def test_sbom_records_optional_production_dependencies_separately():
    payload = sbom_python.build_sbom()

    assert payload["runtime_dependencies"] == []
    optional = payload["optional_production_dependencies"]
    names = {entry["name"] for entry in optional}
    assert {"cryptography", "zstd CLI"} <= names
    assert all(entry["required"] is False for entry in optional)
