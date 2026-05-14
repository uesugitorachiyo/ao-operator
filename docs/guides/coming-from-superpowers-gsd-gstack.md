# Coming From Superpowers, GSD, Or gstack

AO Operator is not a replacement for thinking. It is a local runner for making
your agent workflows repeatable.

For a side-by-side comparison, see
[`ao-operator-vs-superpowers-gsd-gstack.md`](ao-operator-vs-superpowers-gsd-gstack.md).

If you already like Superpowers, GSD, gstack, Spec-Kit, or your own multi-agent
prompt rituals, AO Operator gives those patterns a stable command surface:

- profiles instead of remembering which roles to ask for;
- RunSpecs instead of undocumented prompt chains;
- scoped reads and writes instead of dumping a whole repo into every turn;
- local Codex / Claude Code CLI auth instead of provider API keys;
- artifacts and evidence packs instead of lost chat context.

## Mapping

| Existing habit | AO Operator equivalent |
| --- | --- |
| "Use the planning skill first" | Pick a profile with planner / hardener roles. |
| "Ask one agent to implement and another to review" | Run `bug-fix`, `greenfield`, or `secure-agent` style role chains. |
| "Keep a hand-written task plan in Markdown" | Export `.factory/runspec.yaml` and commit or share it. |
| "Paste context into multiple agents" | Give each role scoped reads, writes, and handoff artifacts. |
| "Review a transcript later" | Review `run-artifacts/<slug>/` and optional evidence packs. |
| "Use subscription CLIs heavily" | Route roles through local `codex` and `claude` CLI auth. |

## First Experiment

Start with a dry-run role graph. It costs no provider tokens and shows the shape
of the autonomous team:

```bash
python3 scripts/factory_run.py specify examples/agent-team-demo/task-brief.md \
  --slug agent-team-demo \
  --profile bug-fix \
  --overwrite-artifacts

python3 scripts/factory_run.py tasks agent-team-demo --profile bug-fix --json
```

Then inspect:

```text
run-artifacts/agent-team-demo/
docs/specs/agent-team-demo-spec.md
docs/plans/agent-team-demo-plan.md
docs/evaluations/agent-team-demo-evaluation.md
```

When you are ready for live provider work, use the same shape with `--run`.
Provider auth still comes from your local CLI sessions.

## What To Judge

Do not judge AO Operator by whether it has the flashiest chat UI. Judge it by
whether it makes your agent work more repeatable:

- Can you see the role graph before provider execution?
- Can you tell which role owns a decision?
- Can you hand the result to another machine or reviewer?
- Can you replay or audit enough context later?
- Can you swap Codex and Claude Code roles without rewriting the workflow?

That is the core value: autonomous local agent work that leaves structure
behind.
