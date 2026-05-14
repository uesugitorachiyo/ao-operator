---
name: closure-verification
description: "Use before claiming completion in AO Operator, claude-agent-teams-v2, codex-agent-teams-v2, or spec-forge-v2. Enforces evidence-first closure: run deterministic tests, self-checks, ledger/status updates, contract conformance checks, and produce evaluator-ready evidence with concerns."
---

# Closure Verification

Use this skill before final response, Evaluator/Closer handoff, release notes, or
any claim that work is done.

## Core Rule

Closure must answer:

- What changed?
- Which spec/plan/contract did it satisfy?
- What commands proved it?
- What remains risky or unverified, and where is the durable artifact?

## Primary Gate

For AO Operator and ai-teams factory repos, run the executable closure gate
first:

```bash
python3 scripts/verify_closure.py --repo . --with-pytest --json
```

Do not claim completion when this returns `FAIL`. Fix the failing evidence and
rerun it.

## Workflow

1. Identify the spec, plan, contract, issue, or user request being closed.
2. Run deterministic checks before writing the final answer.
3. Verify contract/runtime claims directly when the work declares them.
4. Update durable artifacts such as status logs, ledgers, or evaluations when
   the repo expects them.
5. Return a STATUS block or final response with commands and key outputs.

## Load Only If Needed

- `references/factory-closure.md` - factory repo command set and ledgers.
- `references/spec-forge-closure.md` - Spec Forge lint/emit/test checks.
- `references/contract-conformance.md` - direct checks for runtime claims.
- `references/status-output.md` - STATUS block and final response contract.

## Exit Criteria

Closure is ready only when deterministic checks pass or a real blocker is named,
evidence is durable and inspectable, and remaining risk is explicit.
