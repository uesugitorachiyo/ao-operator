# Show HN: AO Operator - local autonomous agent teams for Codex and Claude Code

Demo asset: `images/ao-operator-agent-team.svg`

Secondary demo asset: `docs/assets/hero.gif`

AO Operator is the AI Orchestration Operation layer: a local autonomous agent
CLI for turning Codex and Claude Code subscriptions into repeatable agent
teams. Give it a brief, pick a profile, and it turns that work into planner,
implementer, reviewer, integrator, and closer roles with scoped context, local
CLI auth, RunSpecs, and evidence.

The first user is someone who likes Superpowers, GSD, gstack, Spec-Kit-style
flows, or custom "one agent writes, another reviews" scripts, but wants one
operator surface that is repeatable and inspectable instead of a pile of prompt
rituals.

The short version:

```sh
python3 scripts/factory_run.py tasks \
  financial-services-earnings-note \
  --profile financial-services:earnings-note \
  --json
```

That command renders the financial-services citation-audit role graph. The
profile is plain JSON so an operator can inspect the role order, dependencies,
reads, writes, and provider keys before trusting the run.

## What It Is

AO Operator is a local agent-team runner around AI provider CLIs. A role chain
declares who does the work: planner, implementer, reviewer, integrator,
evaluator-closer, or domain-specific roles like citation audit and compliance
redaction. Each role gets scoped reads, scoped writes, instructions, and
provider routing from `.env`.

The default provider path is local OAuth CLI auth for Codex or Claude Code.
Provider API keys are intentionally rejected because this project is meant to
run from your machine with your existing CLI session.

The operator writes artifacts before it launches provider work. You get a
status directory, rendered prompts, RunSpec YAML, role handoff paths, and
evaluation slots. The important part is not a hidden prompt. It is the ability
to turn local subscription-based agents into a repeatable workflow, inspect what
they are about to do, rerun it, and decide whether the result is acceptable from
evidence instead of vibes.

## Why Try It

- You want more value from Codex or Claude Code subscriptions without switching
  to API-key billing.
- You want autonomous coding/research workflows, but with reviewer and closer
  roles instead of one unbounded agent.
- You want a replacement shell for scattered Superpowers/GSD/gstack-style
  workflows.
- You want workflow files, RunSpecs, and artifacts that survive after the chat
  scroll is gone.
- You want evidence packs when a run matters enough to audit or replay later.

There is also a short migration guide for people coming from those workflows:
`docs/guides/coming-from-superpowers-gsd-gstack.md`.

## The Five Public Repositories

This is one product with supporting repos, not five separate launches:

- `ao-operator` is the entry point and public product.
- `ao-runtime` is the Rust execution engine underneath AO Operator.
- `financial-services-profile` is the flagship citation-audit profile and demo.
- `secure-agent-profile` is the guarded coding-agent profile.
- `ao-control-plane` is the future management layer for typed run state,
  evidence aggregation, and release gates.

The advertisement should point people to AO Operator first. The other repos are
there so the engine, profiles, and future control-plane work are inspectable
instead of hidden in a monorepo.

## The Useful Boundary

The core design boundary is contracts plus replay plus local execution. AO
Operator owns the human-facing contract: brief, shape, role chain, evidence,
closure. AO Runtime owns execution underneath: task DAGs, policy, workspace
isolation, and events. Profiles package domain-specific role graphs and fixtures
without changing the operator.

That boundary matters because the failure mode of many agent tools is hidden
state. The tool "does work," but it is hard to answer simple questions later:
What was the original brief? Which role changed the file? What did the reviewer
actually accept? Which command proved the result? What would need to be rerun?

AO Operator tries to make those answers boring. Role outputs are artifacts.
Gate B checks the plan before execution. Gate R checks closure after execution.
The evaluator-closer has to accept evidence; otherwise the run is not done.

## What It Is Not

It is not an enterprise compliance suite. It does not certify that a financial
note, KYC review, or code change is compliant. It produces citation, policy,
approval, and replay evidence that a human reviewer can inspect.

It is not a multi-provider router. The current provider shim is intentionally
small: Codex and Claude Code through local CLI auth.

It is not a hosted AI dev platform. The launch story is local execution,
autonomous role chains, reviewable contracts, and signed evidence packs.

## Comparisons

Temporal and Restate are stronger general durable-execution systems. AO
Operator is not trying to beat them at general workflow infrastructure. Its
wedge is local coding/research agent teams with policy gates and evidence
packs.

LangGraph, Mastra, OpenHands, Cline, and similar tools are stronger ecosystem
and UI references. AO Operator is narrower: local CLI subscriptions, explicit
role contracts, fail-closed policy, and replayable artifacts.

Factory.ai is the obvious naming collision risk around the word "factory."
That is why the public product is AO Operator. The old internal repository
history should not be the launch narrative.

## The Demo I Would Lead With

The first useful workflow is citation-sensitive work where a reviewer needs a
trail. For example, a boutique research or advisory team wants an AI-assisted
earnings-note draft, but cannot accept unsupported claims. Instead of pasting a
filing into a chat and hoping the result is coherent, they run the
Financial Services Profile and keep the source pack, citation map, compliance
redaction notes, approvals, and evidence pack with the draft.

The second workflow is client-facing AI coding work where you need a trail. A
consultant gets a bug report from a client. Instead of pasting the whole thing
into a chat and hoping the answer is coherent, they put the report in a brief,
run the bug-fix profile, and keep the resulting plan, prompts, review, and
evaluation with the patch.

The third workflow is internal guardrails for a small team. A two-person agency
may not need SOC2, but it still needs to avoid accidental secret exposure,
unclear scope, and unreviewed AI edits. AO Operator's posture is not "trust the
model." It is "state the contract, scope the files, run the role, and close only
when evidence exists."

## Rough Edges

The docs need more screenshots. The financial-services demo currently uses
deterministic public-data fixtures, not paid live market data connectors. AO
Control Plane is early future infrastructure. The first public release should
therefore be honest: AO Operator is usable as a local evidence-producing
operator, while the broader platform is still maturing.

## Why I Built It

I wanted an AI workflow that felt more like a small production line than a chat
window. The inputs should be explicit. The workers should have job descriptions.
The outputs should land in predictable places. The reviewer should not have to
guess what changed. The closer should be allowed to say no.

That is the practical promise of AO Operator: one command to turn a brief into
a traceable AI work package, with enough structure that you can run it again,
hand it to another machine, or show the evidence to someone paying you for the
work.
