"""Regression test for Python 3.14 argparse compatibility.

Python 3.14 added eager validation of help-format strings in
ArgumentParser.add_argument. Any literal `%X` token where X is not a
valid printf format spec (e.g. `%TEMP%`) raises ValueError at
add_argument time — before argv is even parsed. This broke
`scripts/factory_run.py` on Mac default `python3` (3.14.x) because the
--ao-home help string referenced %TEMP% as the Windows tempdir example.

Fix: escape literal % in help strings as %% (argparse de-escapes for
display). This test exercises both the parser-construction path (any
add_argument failure surfaces as non-zero exit) and the rendered help
output (post-de-escape, %TEMP% appears literally for Windows users).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "factory_run.py"


def test_factory_run_help_exits_zero_on_current_python():
    """Constructing the argparse parser must not crash on the Python
    interpreter running this test. On Python 3.14, this guards against
    re-introducing literal '%TEMP%' (or any unescaped percent) in any
    add_argument help= string."""
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--help"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, (
        f"factory_run.py --help failed (exit {result.returncode}). "
        f"stderr tail: {result.stderr[-500:]}"
    )


def test_factory_run_help_renders_temp_token_literally():
    """%%TEMP%% in source must render as %TEMP% in help output (one
    layer of de-escape). Guards against someone reverting the escape
    while making the parser pass with another mechanism."""
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--help"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0
    assert "%TEMP%" in result.stdout, (
        "rendered --help no longer contains the literal Windows tempdir "
        "example; --ao-home help may have regressed"
    )
    # Double-check no leaked double-percent escape remains in display.
    assert "%%TEMP%%" not in result.stdout
