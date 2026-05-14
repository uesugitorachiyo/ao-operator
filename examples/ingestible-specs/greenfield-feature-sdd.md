# Greenfield Feature SDD: Run Summary Command

## Goal

Add a command that summarizes the latest AO Operator run artifacts for a slug.

## User Impact

A user should be able to quickly inspect what a dry-run produced without opening
every generated file manually.

## Proposed Interface

```bash
python3 scripts/factory_run.py summarize <slug> --json
```

The command should report:

- status directory path;
- RunSpec path;
- spec path;
- plan path;
- whether evaluation evidence exists;
- suggested next command.

## Non-Goals

- No live provider execution.
- No web UI.
- No changes to evidence pack format.
- No remote host behavior.

## Role Expectations

- Intake confirms the command shape and output contract.
- Planner identifies the smallest CLI extension.
- Implementer adds the command and tests.
- Reviewer checks missing-slug behavior.
- Evaluator-closer verifies command output against acceptance criteria.

## Acceptance Criteria

- Existing commands keep working.
- Missing slug returns a useful error.
- JSON output is stable enough for docs.
- Tests cover present and missing artifact paths.
