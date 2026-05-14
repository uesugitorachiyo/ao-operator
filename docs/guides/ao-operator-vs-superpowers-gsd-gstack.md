# AO Operator vs Superpowers, GSD, and gstack

AO Operator is for people who already like agent workflows, but want the work
to survive beyond one chat window.

It does not replace planning skills, review habits, or browser QA. It gives
those habits a local operator surface: briefs become profiles, profiles become
role graphs, role graphs become RunSpecs, and RunSpecs produce artifacts that a
reviewer can inspect later.

## The Short Version

| Tooling habit | What is good about it | What AO Operator adds |
| --- | --- | --- |
| Superpowers-style skills | Strong reusable playbooks and discipline | A runnable role graph with scoped inputs, outputs, and closure artifacts |
| GSD-style planning | Clear phase structure and verification gates | A local command path from brief to role artifacts |
| gstack-style QA and launch flow | Practical browser/testing/release muscle | Evidence directories and RunSpecs that make the same flow repeatable |
| Hand-rolled multi-agent scripts | Flexible and fast to invent | Provider routing, profile JSON, policy gates, and consistent status output |
| One big Codex or Claude Code chat | Low setup cost | Role ownership, less context sprawl, and reviewable handoffs |

## Where AO Operator Is Better

- **Repeatability:** the profile and RunSpec show the work shape before live
  provider execution.
- **Local subscription use:** roles call local `codex` or `claude` CLI auth.
  Provider API keys are not part of the public path.
- **Role ownership:** planner, implementer, reviewer, integrator, and closer
  can produce separate artifacts instead of one blended transcript.
- **Audit trail:** status directories and evidence packs make the work easier
  to inspect after the run.
- **Portability:** a `.factory/runspec.yaml` can move across machines or be
  reviewed before execution.
- **Cross-platform coworking:** Ubuntu, macOS, and native Windows workers can
  own different role lanes in one run.

## Where Existing Tools Still Fit

Keep using the skills and habits that help you think clearly. AO Operator is
not trying to be the only interface. A good workflow can be:

```text
idea -> planning habit -> AO Operator profile -> local provider run -> review habit -> evidence pack
```

Use Superpowers/GSD/gstack style thinking to decide what should happen. Use AO
Operator when you want that decision to become a repeatable local run.

For OS-specific product work, see
[`native-cross-platform-coworking.md`](native-cross-platform-coworking.md).

## First Trial

Run the shortest dry-run demo:

```bash
bash scripts/first_run_demo.sh
```

Or start from a copy-pasteable SDD:

```bash
bash scripts/ingest_spec_demo.sh examples/ingestible-specs/bug-fix-sdd.md bug-fix
```

Then inspect:

```text
run-artifacts/agent-team-demo-first-run/
docs/specs/agent-team-demo-first-run-spec.md
docs/plans/agent-team-demo-first-run-plan.md
```

If this feels useful, the next step is to run the same profile with live local
provider CLI auth.
