---
name: spec-forge-contracting
description: "Use when authoring, linting, emitting, or improving Spec Forge v2 or AO Operator contracts. Converts prose intent into EARS/RFC-2119 SHALL statements, acceptance criteria, negative constraints, sensitive-field declarations, and slice reads/writes for AO Operator, claude-agent-teams-v2, and codex-agent-teams-v2."
---

# Spec Forge Contracting

Use this skill when creating or revising `*.contract.json`, emitted specs/plans,
or Spec Forge validator/emitter behavior.

## Workflow

1. Treat the contract as the source of truth for emitted specs, plans, dispatch
   gates, and evaluation evidence.
2. Encode user intent as testable requirements, acceptance criteria, negative
   constraints, sensitive fields, trigger hints, and slices.
3. Lint before emit. If lint fails, patch the contract instead of explaining
   around it.
4. After implementation, verify declared claims directly against files,
   commands, or runtime behavior.

## Load Only If Needed

- `references/contract-schema.md` - required contract fields and readiness.
- `references/requirements-style.md` - EARS/RFC-2119 SHALL statement style.
- `references/slices-and-sensitive-fields.md` - slices, strict globs, sensitive fields, trigger hints.
- `references/lint-emit.md` - lint, emit, pytest, and post-build conformance commands.

## Exit Criteria

A contract is ready only when lint passes, every acceptance criterion has an
exact verification oracle, slices are safe for the chosen dispatch mode, and
manual review requirements are explicit.
