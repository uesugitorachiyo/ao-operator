# AO Operator Profiles

This directory holds **profile-driven role chains** that the runner
(`scripts/factory_run.py`) loads when invoked with `--profile NAME`.
Default behavior with no flag remains the legacy seven-role chain
(equivalent to `default.json`).

> Note: this is distinct from `examples/provider-profiles/`, which
> concerns *provider* env-var presets (which model — Claude or Codex —
> serves which role). Role-chain profiles (this directory) define
> *which roles run, in what order, with what instructions*. The two
> compose: an `evidence` role chain can be run with a `codex`
> provider profile or a `claude` provider profile.

## Schema

Every profile is a single JSON document. Schema version: `ao-operator/profile/v1`.
Top-level profiles live at `profiles/<name>.json`; namespaced profiles live at
`profiles/<namespace>/<workflow>.json` and load as
`<namespace>:<workflow>` (for example, `financial-services:earnings-note`).

The first public demo profile is `financial-services:earnings-note`: a
citation-audit workflow over public SEC EDGAR source data. Starter coding
profiles remain useful examples, but they are not the launch wedge.

Runtime boundary: `profiles/financial-services/*.json` are AO Operator-side
role-chain contracts. The live financial-services implementation now lives in
the standalone `financial-services-profile` repo; `factory_run.py --profile
financial-services:* --run` points operators to `fsp run ... --engine ao`.
Dry-run and `tasks`/`plan` aliases remain useful for inspecting the role graph.

| Field | Type | Required | Notes |
|---|---|---|---|
| `profile` | str | yes | Must equal the filename stem (e.g. `default.json` -> `"profile": "default"`) |
| `schema` | str | yes | Literal `"ao-operator/profile/v1"` |
| `version` | int | yes | Literal `1` |
| `description` | str | yes | One-paragraph human description |
| `common_instructions` | list[str] | yes | Shared instructions prepended to every role's prompt |
| `roles` | list[role] | yes | Ordered DAG nodes; first role has empty `deps` |
| `policy_posture` | dict | optional | Reserved for private security profiles |

### Per-role fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | str | yes | Unique within profile; see id conventions below |
| `role` | str | yes | Human label, e.g. `"Planner Intake"` |
| `provider_key` | str | yes | Existing `FACTORY_V3_*_PROVIDER` env var |
| `deps` | list[str] | yes | Sibling role ids; may be empty |
| `reads` | list[str] | yes | Path tokens (literal `<slug>` is expanded by the runner) |
| `writes` | list[str] | yes | Same as `reads` |
| `skills` | list[str] | yes | Relative paths under `skills/`; may be empty |
| `instructions` | list[str] | yes | Per-role instructions appended to `common_instructions` |
| `is_mutator` | bool | optional | Override `is_mutator_task(id)` for non-`implementer-slice` mutators |
| `deterministic` | bool | optional | Marks a non-LLM role whose outputs can be replay-checked without provider calls |
| `replay_command` | list[str] | required when `deterministic` is `true` | Declarative command used as the replay contract; it is recorded and validated by default, and only executed when replay runs with `--execute-deterministic` |
| `replay_outputs` | list[str] | required when `deterministic` is `true` | Output filenames that must resolve to the role's content-addressed artifacts |

Deterministic replay metadata is also accepted in topology `spec:` blocks using
the same snake_case field names. Evidence-pack replay validates these
declarations and confirms declared outputs are present in CAS by default. The
operator must pass `--execute-deterministic` to run replay commands; execution
uses no shell, a minimal environment, a timeout, and denies common network
clients. It does not call Codex, Claude, AO, or LLM providers.

### Id conventions (preserved)

To keep the runner's `is_mutator_task` and slice fan-out working, use
these names:

- `implementer-slice` — single-slice mutator (fans out under `--slices N`)
- `<name>-factory` — multi-slice mutator
- `<name>-reviewer` or `*-slice` reviewer — judged by `_is_slice_reviewer`
- `factory-manager`, `integrator`, `evaluator-closer` — exact-match roles

New ids that don't match the above (e.g. `intake`, `policy-binder`) are
treated as plain linear roles and bypass slice fan-out — appropriate for
linear profiles like `evidence`.

## Adding a profile

1. Create `profiles/<NAME>.json` matching the schema above.
2. Set `"profile": "<NAME>"` to match the filename stem.
3. Add a shape test under `tests/test_factory_run_<NAME>_profile.py`
   that asserts the role count, DAG structure, terminal write
   target, and field types. Use
   `tests/test_factory_run_evidence_profile.py` as a template.
4. Run `python3 -m pytest tests/test_factory_run_<NAME>_profile.py`.
5. The runner CLI will auto-discover the profile via
   `--profile <NAME>` once the loader (T4-IMPL) is wired in
   `scripts/factory_run.py`.

## Reference

- Design doc: `run-artifacts/release-v0.1/mac/profile-design.md`
- Implementation contract: `run-artifacts/release-v0.1.1/T4-SPEC.md`
- Provider env routing (orthogonal): `examples/provider-profiles/README.md`
- Financial-services scaffold input:
  `briefs/financial-services-inventory.md`
