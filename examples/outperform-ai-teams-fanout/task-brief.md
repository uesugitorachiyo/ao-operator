# Outperform ai-teams Fanout Task Brief

Build a greenfield multi-tenant analytics workbench for product teams.

Use AO Operator to outperform a tightly coupled ai-teams workflow by making the
work parallel, artifact-driven, and provider-selectable.

This example must include a Spec Forge contract and a Ralph Loop gate before
any implementation branch dispatches. Spec Forge defines the machine-checkable
SHALLs, slice read/write scopes, sensitive fields, and negative constraints.
Ralph Loop verifies the greenfield readiness gate and rejects fan-out if the
contract is too vague or branch ownership overlaps.

## Product Scope

The implemented application should include:

- Tenant-aware project and user model.
- Event ingestion API with validation and append-only activity storage.
- Dashboard UI for event trends, project health, and recent activity.
- Background summarizer interface for daily project insights.
- Quality harness covering contracts, smoke flows, security boundaries, and
  performance budgets.
- Setup documentation and sample prompts.

## Factory Shape

Shape it as greenfield.

AO Operator must split the work into independent branches only where writes are
disjoint:

- `contract-factory`: owns API schema, shared types, and acceptance fixtures.
- `backend-factory`: owns ingestion, storage, auth boundaries, and service tests.
- `frontend-factory`: owns dashboard UI, state handling, and accessibility checks.
- `quality-factory`: owns test harness, security checks, and performance budgets.
- `docs-factory`: owns setup docs, prompt examples, and operator runbooks.

## Throughput Goal

Compared with a tightly coupled ai-teams run, AO Operator should reduce critical
path time by running implementation factories in parallel after plan hardening
and by fanning in only durable artifacts.

Expected execution waves:

- Wave 1: planner-intake, Spec Forge contract emission, Ralph Loop gate, and
  plan-hardener.
- Wave 2: factory-manager dispatches contract, backend, frontend, quality, and
  docs factories in parallel
  where their write sets are disjoint.
- Wave 3: reviewers for each branch in parallel.
- Wave 4: integrator and evaluator-closer.

## Constraints

- Use OAuth CLI providers only.
- Do not configure `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.
- Do not pass full transcripts between branches.
- Do not read secrets.
- Do not dispatch implementation branches until Spec Forge and Ralph Loop gates
  pass.
- Every branch must return `Result`, `Artifact`, `Evidence`, `Concerns`, and
  `Blocker`.
- Evaluator closure must reject if any branch returns `BLOCKED` or `REJECTED`.

## Acceptance Criteria

- AO Operator emits a spec, hardened plan, materialized prompts, RunSpec, status
  log, AO events, role artifacts, and evaluation artifact.
- The example includes `spec-forge.contract.json` with SHALLs, acceptance
  criteria, negative constraints, sensitive fields, and slices.
- The AO topology includes explicit `spec-forge-contract` and `ralph-loop`
  tasks before `factory-manager`.
- The plan identifies disjoint write ownership for each factory branch.
- The AO topology has explicit fan-out/fan-in dependencies.
- Codex and Claude provider selections are resolved from `provider.env`.
- The final evaluation references each branch artifact and the AO run id.
