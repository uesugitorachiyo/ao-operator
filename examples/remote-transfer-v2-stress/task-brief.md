# Remote Transfer v2 Stress Task Brief

Use AO Operator to create a maximum-pressure complex dry-run plan for AO
Runtime Remote Transfer v2.

Shape it as greenfield.

## Goal

Materialize a very large AO Operator topology for Remote Transfer v2 planning:
1000 implementation factories, 1000 reviewer branches, and
standard Spec Forge, Ralph Loop, integrator, and evaluator gates.

This is a AO Operator stress test. The run should push task count, prompt
materialization, provider resolution, RunSpec generation, exact prompt
validation, and contract validation. It should not run live provider work.

## Product Scope

The generated plan covers Remote Transfer v2 from connection identity through
remote Codex smoke, operator telemetry, failure recovery, and transfer security.

## Factory Shape

Shape: greenfield.

The topology must include one factory and one reviewer for each Remote Transfer
v2 work domain. Every factory owns disjoint documentation or source-path scopes
declared in `spec-forge.contract.json`.

## Constraints

- Use OAuth CLI providers only.
- Do not configure `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.
- Do not read or transfer provider auth files.
- Do not bind anonymous write-capable endpoints.
- Do not execute live Mac-to-Ubuntu provider work from this dry-run lane.
- Do not pass full provider transcripts between roles.
- Every role must return Result, Artifact, Evidence, Concerns, and Blocker.

## Acceptance Criteria

- AO Operator materializes all 2007 topology tasks.
- The generated RunSpec contains every stress factory and reviewer task.
- Prompt directory exactly matches the topology task IDs.
- Spec Forge contract declares all 1000 slices with reads, writes, and
  verification commands.
- Validator accepts topology sizes above the original 17-task demo.
- `validate_factory.py` and `validate_intake.py` both return PASS.
