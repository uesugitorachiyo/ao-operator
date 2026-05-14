# Provider routing in ao-operator

## Why per-role provider selection exists

AO Operator routes each AO role through the `FACTORY_V3_*_PROVIDER` env-var
family in `.env.example`.
Each value must resolve to `codex` or `claude`.
This keeps provider choice local to the role instead of hard-coding it in the
AO topology or prompts.
The model also preserves OAuth CLI-only auth and avoids provider API-key paths.

## Default routing as of 2026-05-02

| Mutator role | Default provider |
| --- | --- |
| planner-intake | codex |
| plan-hardener | claude |
| factory-manager | codex |
| implementer-slice | codex |
| reviewer-slice | claude |
| integrator | codex |
| evaluator-closer | codex |

## Why evaluator-closer defaults to codex

Commit `fe7e096` captured the evaluator-closer routing decision from burn-in
#2: `factoryv3-burnin-2-show-providers` compared with
`factoryv3-burnin-2-show-providers-codex-eval`.
With claude on a code-modification task, evaluator closure over-blocked with
the failure modes "AO not yet completed" and "Cannot verify acceptance criteria
without implementer artifacts".
That is a prompt-fix gap, not a permanent product decision.

## When to switch evaluator-closer back to claude

Doc-shape work has not been observed to hit the regression.
For docs-only runs, claude is a valid evaluator-closer choice and may save
codex tokens.
Maintainers should switch only when the run shape and evidence do not require
the code-modification closure behavior that triggered burn-in #2.

## Open follow-up

The prompt-hardening task `overnight-1-evaluator-prompt-harden` remains open.
Until that lands, codex is the correct evaluator-closer default.
