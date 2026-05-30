---
name: plan-hardener
description: "Use for AO Operator plan-hardener roles that convert an accepted intake/spec into an execution-ready plan. Enforces shape-specific lint rules, bounded self-review, verification oracles, scoped writes, and explicit blocker semantics before factory-manager fan-out."
---

# Plan Hardener

Use this skill after planner-intake has produced a spec and before
factory-manager chooses fan-out. The role hardens the plan; it does not
dispatch providers, run AO, wrap `factory_run.py`, or introduce roles/gates that
are absent from the materialized DAG.

## Workflow

1. Read the injected spec, scoped reads/writes, sensitive fields, negative
   constraints, and acceptance criteria.
2. Classify the shape as `greenfield`, `bug-fix`, or `refactor`; if the shape is
   missing or contradictory, return `BLOCKED`.
3. Run at most five internal hardening passes. Stop earlier when every lint rule
   below is satisfied; do not loop indefinitely or retry the whole run.
4. Produce an execution-ready plan with concrete slices, disjoint write
   ownership, verification commands, rollback/cleanup notes, and closure
   evidence expectations.
5. Return `DONE` when the plan is dispatch-ready, `DONE_WITH_CONCERNS` when the
   plan is usable with named residual risk, or `BLOCKED` when required context
   is missing. For missing context, set `Blocker: NEEDS_CONTEXT: <exact field>`.

## Shape Lint Rules

Greenfield:
- Acceptance criteria must name observable behavior, output paths, and
  verification commands.
- Slices must have concrete scoped writes or explicitly justify N=1 fallback.
- Sensitive fields and negative constraints must be present before fan-out.

Bug-fix:
- The plan must name the failing behavior, expected behavior, likely regression
  surface, and a test that fails before the fix or equivalent deterministic
  reproduction evidence.
- The write scope must stay close to the root cause; broad rewrites are blockers.

Refactor:
- The plan must state preserved behavior, compatibility constraints, migration
  risk, and regression tests.
- Behavior-changing work must be split out or explicitly blocked.

All shapes:
- Reject overlapping concrete writes unless one owner is explicitly the
  integrator rejoin artifact.
- Reject vague acceptance such as "works", "improve", or "clean up" without an
  oracle.
- Do not require live-provider, network, or secret access unless the spec
  explicitly authorizes it.
- Do not add Ouroboros-style MCP servers, event stores, lineage systems, or
  outer retry loops around AO Operator.

## Exit Criteria

The hardened plan is ready only when factory-manager can choose N=1 or N>1 from
explicit evidence, every slice has reads/writes/verification, Gate B can inspect
the partition, and unresolved blockers are specific enough for the operator or
planner-intake to fix.
