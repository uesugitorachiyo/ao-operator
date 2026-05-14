"""Tests for FACTORY_V3_WORKTREE_ROOT env override + tempdir-based default.

The default WORKTREE_ROOT is computed at module import time. These tests
exercise the underlying ``_resolve_worktree_root`` resolver directly so they
do not depend on import-time evaluation order.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Make scripts/ importable, mirroring the convention used in the existing
# tests (e.g. tests/test_runtime_blockers.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import factory_run  # noqa: E402


def test_resolve_worktree_root_defaults_to_tempdir(monkeypatch):
    monkeypatch.delenv(factory_run.WORKTREE_ROOT_ENV, raising=False)
    expected = Path(tempfile.gettempdir()) / "ao-operator-worktrees"
    assert factory_run._resolve_worktree_root() == expected


def test_resolve_worktree_root_honours_env_override(monkeypatch, tmp_path):
    override = tmp_path / "custom-worktree-root"
    monkeypatch.setenv(factory_run.WORKTREE_ROOT_ENV, str(override))
    assert factory_run._resolve_worktree_root() == override
