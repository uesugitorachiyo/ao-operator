"""Pytest configuration for ao-operator tests.

Adds ao-operator's root and `scripts/` directory to sys.path so test files can
import both `scripts.factory_run` and `factory_run`. factory_run is a CLI
module, not an installable package, so this is the standard pattern for
testing CLI scripts in-tree.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
