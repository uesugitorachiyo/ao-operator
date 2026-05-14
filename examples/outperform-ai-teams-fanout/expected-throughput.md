# Expected Throughput

This example is not claiming a universal benchmark. It defines the conditions
under which AO Operator should outperform a tightly coupled ai-teams run.

## Baseline ai-teams Critical Path

A tightly coupled run typically forces complex work through one shared context:

```text
planner -> hardener -> implementer A -> reviewer A -> implementer B
  -> reviewer B -> implementer C -> reviewer C -> integrator -> closer
```

The cost grows with:

- Shared context size.
- Sequential reviewer handoffs.
- Repeated restatement of branch state.
- Coupled failure recovery.

## AO Operator Critical Path

AO Operator should use AO fan-out:

```text
planner -> Spec Forge -> Ralph Loop -> hardener -> factory-manager
  -> [contract, backend, frontend, quality, docs in parallel]
  -> [branch reviewers in parallel]
  -> integrator -> evaluator
```

## Success Metrics

- Parallel branch count: at least 5 independent implementation factories.
- Shared transcript handoff: 0 full transcripts.
- Provider substitution: 0 occurrences.
- Branch artifact contract: 100 percent of branches return `Result`,
  `Artifact`, `Evidence`, `Concerns`, and `Blocker`.
- Closure gate: reject if any branch is `BLOCKED` or `REJECTED`.
- Critical-path reduction target: at least 30 percent fewer serialized role
  turns than the equivalent tightly coupled run.
- Gate completeness: Spec Forge and Ralph Loop both run before fan-out.

## Why The Topology Should Beat ai-teams

The ai-teams path serializes most work through one role chain, so total time
approaches the sum of all implementation and review slices. The AO Operator
example pays a small upfront cost for Spec Forge and Ralph Loop, then pushes the
five independent factories into the same AO wave and fans in only their
artifacts. That changes the dominant term from total branch work to the slowest
branch, plus integration and closure.

## Failure Conditions

This example should be considered failed if:

- Any branch has overlapping write ownership without an explicit integrator
  contract.
- Any downstream prompt embeds a full provider transcript.
- Any Claude role silently runs as Codex, or any Codex role silently runs as
  Claude.
- Evaluator accepts while a branch artifact is blocked or rejected.
