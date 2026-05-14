# AI Agent Destructive-Action Approval Gate

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that every AO Operator / AO Runtime destructive path
(`rm`, `git reset --hard`, `git push --force`, `git branch -D`,
`db drop`, transfer cleanup, approval revocation, etc.) requires a
fresh, scoped, single-use approval token at execution time, not
just a policy declaration. The gate is fail-closed against the five
highest-risk approval-state-machine hazards: a stale approval reused
after expiry MUST be rejected; an approval whose scope is widened at
execute time (different target, op, operator, or blast radius) MUST
be rejected; the same approval consumed twice for distinct
destructive ops MUST be rejected; a destructive op that runs with a
policy-only declaration ("approval allowed") instead of a
materialized token MUST be rejected; and a parent process approval
inherited by a child without re-confirmation MUST be rejected.

## Contract

`scripts/check_ai_agent_destructive_action_approval.py` emits
`ao-operator/ai-agent-destructive-action-approval/v1`.

The gate runs six deterministic cases (one control PASS + five
mutations FAIL) against an in-process destructive-action approval
state machine with fixed synthetic placeholder identifiers
(`operator_alpha`, `approval_token_zeta`, `approval_token_eta`,
`approval_token_parent_theta`, `git_reset_hard`,
`git_branch_delete_force`, `feature/x`, `main`, `high`,
`2026-05-08T00:00:00+00:00`, `2026-05-08T01:00:00+00:00`,
`2026-05-08T00:30:00+00:00`, `2026-05-08T02:00:00+00:00`). Each case
persists a per-case
`destructive-action-approval-transcript.json` to a temporary work
directory and records `observed_verdict` next to
`expected_case_verdicts`.

Cases:

- `clean_destructive_action_with_fresh_scoped_approval_executes` —
  control: a destructive op runs against a fresh, scope-matched,
  unconsumed approval token before its expiry; the verifier produces
  no errors.
- `stale_approval_reused_after_expiry_rejected` — mutation: a
  destructive op presents a token whose `expires_at` is in the past
  relative to `now`; the verifier records
  `stale_approval_reused_after_expiry`.
- `approval_scope_widened_at_exec_silently_accepted_rejected` —
  mutation: a destructive op presents a token issued for a narrow
  target (`feature/x`) but executes against a wider target (`main`);
  the verifier records `approval_scope_widened_at_exec`.
- `approval_consumed_twice_for_distinct_destructive_ops_rejected` —
  mutation: the same token is consumed twice in a row; the verifier
  records `approval_consumed_twice` for the second consumption.
- `destructive_op_runs_with_policy_only_without_token_rejected` —
  mutation: a destructive op runs against a policy declaration
  ("approval allowed") with no materialized token; the verifier
  records `policy_only_destructive_op_without_token`.
- `parent_process_approval_inherited_by_child_without_reconfirm_rejected`
  — mutation: a child process presents its parent's token without
  issuing a fresh, child-scoped approval; the verifier records
  `child_process_inherited_parent_token_without_reconfirm`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not write inside the repo working tree.
- Do not introduce randomness — all cases are deterministic with
  fixed synthetic operator, token, op, target, blast-radius, and
  ISO-8601 timestamp literals.
- Do not derive approval state from real production approvals,
  operator identities, or destructive op names.

## Verification

```bash
python3 -m pytest -q tests/test_check_ai_agent_destructive_action_approval.py
python3 scripts/check_ai_agent_destructive_action_approval.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/ai-agent-destructive-action-approval.json
```
