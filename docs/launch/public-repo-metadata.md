# Public Repository Metadata

Date: 2026-05-13

Use one public product narrative: **AO Operator** is the product and entry
point. Define **AO** on first mention as **AI Orchestration Operation**. The
other repositories are supporting layers, profiles, or future infrastructure.

## Repository Descriptions

| Repository | Description |
| --- | --- |
| `ao-operator` | AI Orchestration Operation layer: local autonomous agent CLI for turning Codex, Claude Code, OpenClaw, and Hermes-style work into repeatable agent teams. Start here. |
| `ao-runtime` | Rust execution engine under AO Operator: policy-gated DAGs, events, artifacts, workers, OpenClaw/Hermes/MCP/A2A adapters. |
| `financial-services-profile` | AO Operator profile for citation-sensitive financial workflows with signed, replayable evidence packs. |
| `secure-agent-profile` | AO Operator profile for guarded coding-agent workflows, policy decisions, isolated workspaces, and evidence packs. |
| `ao-control-plane` | Future AO management layer for typed run state, evidence aggregation, and release-train gates. |

## Topics

| Repository | Topics |
| --- | --- |
| `ao-operator` | `ai-agents`, `codex`, `claude-code`, `openclaw`, `hermes`, `local-first`, `agent-orchestration`, `evidence-packs`, `policy-gates`, `runbooks` |
| `ao-runtime` | `rust`, `ai-agents`, `durable-execution`, `dag-scheduler`, `policy-engine`, `openclaw`, `hermes`, `mcp`, `a2a`, `local-first`, `ao-operator` |
| `financial-services-profile` | `ao-operator`, `financial-services`, `citation-audit`, `sec-edgar`, `evidence-packs`, `compliance-review`, `ai-agents` |
| `secure-agent-profile` | `ao-operator`, `secure-coding`, `ai-agents`, `policy-gates`, `secret-scanning`, `evidence-packs`, `code-review` |
| `ao-control-plane` | `ao-operator`, `control-plane`, `run-state`, `evidence-packs`, `release-gates`, `ai-agents` |

## Launch Rule

External copy should say:

> Start with AO Operator. AO means AI Orchestration Operation. AO Runtime is the
> engine underneath it, including the OpenClaw adapter, Hermes plugin bridge,
> MCP, and A2A surfaces. Profiles are runnable examples and domain packages. AO
> Control Plane is future management infrastructure.

Avoid presenting the repos as independent products on first contact.
