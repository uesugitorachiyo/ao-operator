---
name: context-offload
description: "Use during large research, codebase scans, parallel review, or long factory sessions to keep parent context clean. Offloads high-volume reads to fresh subagents, returns manifests instead of bodies, applies model-tier routing, and triggers session handoff before context rot."
---

# Context Offload

Use this skill when a task needs large file reads, broad search, parallel review,
or more than a few turns of sustained work.

## Workflow

1. Decide whether the next useful work is local, delegated, or durable handoff.
   Keep urgent blocking work local.
2. Offload broad reads, independent reviews, verification, or exploratory
   research when the result can return as a compact manifest.
3. Send each subagent a narrow scope, explicit ownership, and a return contract.
4. Keep the parent context to paths, short findings, decisions, risks,
   commands, and final evidence.
5. Trigger handoff before context pollution affects implementation quality.

## Load Only If Needed

- `references/delegation-policy.md` - when to offload and what to keep local.
- `references/prompt-contracts.md` - read-only, review, coding, and verifier
  prompt shapes.
- `references/model-routing.md` - model-tier selection and parallelism rules.
- `references/handoff-state.md` - durable handoff triggers and summary format.

## Exit Criteria

The parent has a compact manifest, not raw bodies or logs; delegated edits have
clear ownership; durable decisions live in repo artifacts when the work spans
turns, repos, or phases.
