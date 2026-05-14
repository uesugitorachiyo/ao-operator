from __future__ import annotations

import factory_doctor


def test_factory_doctor_uses_ao_exe_candidate_on_windows(tmp_path, monkeypatch):
    runtime = tmp_path / "ao-runtime"
    release = runtime / "target" / "release"
    release.mkdir(parents=True)
    (release / "ao.exe").write_text("stub", encoding="utf-8")

    monkeypatch.setattr(factory_doctor, "_is_windows", lambda: True)

    ao_bin = factory_doctor._ao_binary_candidate(runtime)

    assert ao_bin == release / "ao.exe"


def test_factory_doctor_has_no_llm_wiki_checks(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTORY_V3_LLM_WIKI_PATH", str(tmp_path / "wiki"))

    checks = factory_doctor.run_checks(str(tmp_path / "missing.env"))
    check_ids = {check["id"] for check in checks}

    assert "path:llm_wiki" not in check_ids
    assert "cli:qmd" not in check_ids


def test_factory_doctor_requires_windows_git_longpaths(monkeypatch, tmp_path):
    def fake_git_config(key: str) -> str:
        return {
            "core.longpaths": "false",
            "core.filemode": "false",
        }.get(key, "")

    monkeypatch.setattr(factory_doctor, "_is_windows", lambda: True)
    monkeypatch.setattr(factory_doctor, "_git_config_value", fake_git_config)

    checks = factory_doctor.run_checks(str(tmp_path / "missing.env"))
    by_id = {check["id"]: check for check in checks}

    assert by_id["git.windows.longpaths"]["status"] == "fail"
    assert "git config core.longpaths true" in by_id["git.windows.longpaths"]["message"]
    assert by_id["git.windows.filemode"]["status"] == "ok"
