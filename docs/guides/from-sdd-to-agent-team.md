# From SDD To Agent Team

AO Operator is useful when the input is more structured than a casual prompt:
an SDD, bug report, feature brief, security profile, or planning note.

The workflow is intentionally simple:

```text
SDD / brief -> profile -> role graph -> RunSpec -> role artifacts -> closure
```

The important part is not that AO Operator has "agents." The important part is
that each agent role has a narrow job, scoped context, and an artifact contract.

![AO Operator spec to agent team flow](../../images/ao-operator-spec-to-agents.svg)

## What AO Operator Took From Public Agent Workflows

AO Operator borrows the practical parts of public skill and planning systems:

- **Skills:** reusable role instructions and operating discipline.
- **SDDs:** explicit goals, non-goals, interfaces, risk, and verification.
- **GSD-style planning:** phase boundaries, acceptance criteria, and closure.
- **gstack-style verification:** browser/test/release evidence over optimism.
- **Spec-Kit-style commands:** `specify`, `plan`, `tasks`, and `analyze`.

The difference is packaging. AO Operator turns those ideas into a runnable local
workflow instead of leaving them as advice inside a chat transcript.

For products that must work across multiple operating systems, the same
workflow can route lanes to Ubuntu, macOS, and native Windows workers. See
[`native-cross-platform-coworking.md`](native-cross-platform-coworking.md).

## How Roles Are Used

| Role | Optimized for | Receives | Produces |
| --- | --- | --- | --- |
| `intake` | ambiguity reduction | the original SDD or brief | clarified scope, blockers, assumptions |
| `planner` | token-efficient decomposition | scope + constraints | the smallest useful plan and test proof |
| `implementer` | bounded code change | plan + scoped files | patch and implementation notes |
| `reviewer` | adversarial check | patch + acceptance criteria | risks, missed cases, required fixes |
| `integrator` | combining evidence | role outputs | final package and consistency check |
| `evaluator-closer` | completion decision | evidence + acceptance criteria | accept / reject verdict |

This is why it can be cheaper and clearer than one large chat. The planner does
not need all implementation logs. The reviewer does not need the whole planning
conversation. The closer should read evidence, not guess from a transcript.

## Try The Ingestible Specs

Copy one of the sample specs and run it:

```bash
bash scripts/ingest_spec_demo.sh examples/ingestible-specs/bug-fix-sdd.md bug-fix
```

Then inspect:

```text
run-artifacts/ingest-bug-fix-sdd/
docs/specs/ingest-bug-fix-sdd-spec.md
docs/plans/ingest-bug-fix-sdd-plan.md
```

The default run is provider-free. It shows the role graph and artifacts before
spending local Codex or Claude Code subscription time.

## When To Use Each Profile

| Input type | Recommended profile | Why |
| --- | --- | --- |
| narrow bug report | `bug-fix` | keeps implementation small and reviewer-focused |
| new feature SDD | `greenfield` | adds architecture and acceptance boundaries |
| behavior-preserving change | `refactor` | forces non-regression proof |
| docs update | `doc-update` | avoids heavyweight implementation roles |
| verification-only question | `smoke-test` | read-only checks without patching |

## What To Judge

After the run, judge AO Operator by the artifacts:

- Did the role graph match the work?
- Did the plan narrow the task?
- Were assumptions and blockers explicit?
- Did the RunSpec make the workflow portable?
- Could a reviewer understand the outcome without reading a long chat?
