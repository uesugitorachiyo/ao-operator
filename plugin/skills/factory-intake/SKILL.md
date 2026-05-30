---
name: factory-intake
description: "Use before non-trivial AO Operator, claude-agent-teams-v2, or codex-agent-teams-v2 work to turn user intent into a spec-first, Shape-aware, verification-backed factory intake. Applies Spec Forge when a machine-checkable contract is useful, requires negative constraints, slices, sensitive fields, and explicit verification before dispatch."
---

# Factory Intake

Use this skill before MODERATE or COMPLEX factory work, and for any task likely
to touch multiple files, providers, auth, docs, UI, storage, or agent routing.

## Workflow

1. Classify the task as TRIVIAL, MODERATE, or COMPLEX and choose `Shape:
   greenfield | bug-fix | refactor`.
2. Convert the request into a bounded intake artifact before implementer
   dispatch. Do not dispatch from a loose prompt.
3. Add verification, negative constraints, sensitive fields, trigger hints, and
   slices before any fan-out.
4. Run the executable intake validator before dispatch:

```bash
python3 scripts/validate_intake.py <contract-or-spec> --json
```

## Load Only If Needed

- `references/intake-artifact.md` - required fields and ready-to-dispatch checklist.
- `references/spec-forge.md` - when and how to produce Spec Forge artifacts.
- `references/shape-gates.md` - Gate B and Gate R intake requirements.
- `references/offload-contract.md` - bounded subagent research return format.

## Exit Criteria

Return or dispatch only after the intake has explicit `Classification` and
`Shape`, evidence-tied success criteria, scoped `reads`/`writes`, sensitive
fields, trigger hints, negative constraints, and zero unresolved blockers.
