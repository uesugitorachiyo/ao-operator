"""Regression tests for extract_scoped_writes() in factory_run.

This helper (added in PR #12, closes #8) scans a brief for file-edit
declarations and returns the paths the spec's `## Scoped Writes` block
must include alongside ao-operator's metadata writes. factory-manager
BLOCKs on Scoped Writes mismatches, so a regression here is high-impact.

The function is regex-based and easy to break — these tests pin the
contract: trigger phrases ("file edit", "new file", "edit:"), path
filtering (must contain `/` or end with a recognized extension),
quote/punctuation stripping, dedup, and the "no false positives from
prose" requirement.
"""
from __future__ import annotations

import factory_run

extract = factory_run.extract_scoped_writes


def test_empty_brief_returns_empty_list():
    assert extract("") == []


def test_brief_with_no_file_declarations_returns_empty_list():
    brief = """
    # My Task

    This task does not declare any specific files.
    It just describes high-level intent.
    """
    assert extract(brief) == []


def test_one_file_edit_with_path():
    brief = "## Scope\n\nOne file edit: scripts/factory_run.py"
    assert extract(brief) == ["scripts/factory_run.py"]


def test_two_file_edits_phrase():
    brief = "Two file edits: scripts/x.py"
    assert extract(brief) == ["scripts/x.py"]


def test_three_file_edits_phrase():
    brief = "Three file edits: docs/notes.md"
    assert extract(brief) == ["docs/notes.md"]


def test_new_file_phrase():
    brief = "- New file: claude-agent-teams-v2/scripts/dispatch.py"
    assert extract(brief) == ["claude-agent-teams-v2/scripts/dispatch.py"]


def test_edit_phrase_lowercase():
    brief = "- edit: scripts/factory_doctor.py"
    assert extract(brief) == ["scripts/factory_doctor.py"]


def test_bullet_dash_prefix_supported():
    brief = "- One file edit: scripts/foo.py\n- New file: scripts/bar.py"
    assert extract(brief) == ["scripts/foo.py", "scripts/bar.py"]


def test_strips_backticks_and_quotes():
    brief = 'New file: `scripts/foo.py`\nEdit: "scripts/bar.py"'
    assert extract(brief) == ["scripts/foo.py", "scripts/bar.py"]


def test_strips_trailing_punctuation():
    brief = "New file: scripts/foo.py.\nEdit: scripts/bar.py,\nEdit: scripts/baz.py;"
    assert extract(brief) == [
        "scripts/foo.py",
        "scripts/bar.py",
        "scripts/baz.py",
    ]


def test_recognized_extension_without_slash_matches():
    """Single-segment filenames are accepted if they end in a recognized
    extension. Useful for repo-root files like pyproject.toml or .env.example."""
    brief = "Edit: pyproject.toml"
    assert extract(brief) == ["pyproject.toml"]


def test_unrecognized_extension_without_slash_skipped():
    """A path with no slash and no recognized extension is treated as prose
    (e.g., a description, not a file)."""
    brief = "Edit: README"
    assert extract(brief) == []


def test_dedup_preserves_first_order():
    brief = """
    One file edit: scripts/factory_run.py
    Edit: scripts/factory_run.py
    New file: scripts/new.py
    """
    assert extract(brief) == ["scripts/factory_run.py", "scripts/new.py"]


def test_prose_mention_does_not_match():
    """The brief that introduced this helper explicitly required: prose
    mentions like 'modify the scripts/factory_run.py file later' must NOT
    pollute scoped_writes. Only lines with trigger phrases match."""
    brief = "We will later modify the scripts/factory_run.py file."
    assert extract(brief) == []


def test_recognized_extensions_full_set():
    """All seven recognized extensions are accepted."""
    brief = """
    Edit: a.py
    Edit: b.md
    Edit: c.sh
    Edit: d.toml
    Edit: e.yaml
    Edit: f.yml
    Edit: g.json
    """
    assert extract(brief) == ["a.py", "b.md", "c.sh", "d.toml", "e.yaml", "f.yml", "g.json"]


def test_realistic_multi_section_brief():
    """End-to-end: a realistic brief with prose, mixed declarations,
    and unrelated file mentions in code blocks resolves to only the
    declared scope."""
    brief = """# My Bug Fix Brief

Some intro about why this matters.

## Scope

- One file edit: scripts/factory_run.py
- New file: tests/test_thing.py

## Failing reproducer evidence

```bash
grep -n "something" scripts/other_unrelated.py
```

We will later look at scripts/another_unrelated.py too.
"""
    assert extract(brief) == ["scripts/factory_run.py", "tests/test_thing.py"]
