# AO Operator Skills

AO Operator vendors the shared ai-teams factory skill set so the scaffold can run
without depending on another repo at skill-use time.

## Inventory

- `factory-intake` - Shape-aware intake, Spec Forge, gates, slices, and
  verification.
- `plan-hardener` - shape-specific plan linting, bounded hardening, and
  dispatch-ready verification oracles.
- `context-offload` - bounded research, model-tier routing, and handoff state.
- `closure-verification` - evidence-first closure and contract conformance.
- `mission-monitor-ops` - dashboard startup, endpoint checks, and artifact
  visibility.
- `spec-forge-contracting` - SHALL statements, acceptance criteria, sensitive
  fields, and slice contracts.
- `llm-wiki-lookup` - manual read-only lookup against an external llm-wiki
  checkout when explicitly requested.
- `citation-audit` - financial-services claim-to-source citation gate for
  numeric and quoted claims.
- `compliance-redact` - financial-services Reg FD / MNPI / PII scrub before
  supervisory review.

## Policy Scripts

Repo-local validators live in `scripts/`:

```bash
python3 scripts/validate.py
python3 scripts/validate_intake.py <contract-or-spec> --json
python3 scripts/verify_closure.py --repo . --with-pytest --json
python3 scripts/code_smell_analyzer.py <paths> --json
```

## Global Install

To make these skills visible to Claude Code and Codex globally from this
AO Operator checkout:

```bash
python3 scripts/install_global.py --confirm-global-skill-install
```

This changes `~/.claude/skills` and `~/.codex/skills`, so do not run it when
you want to keep the global ai-teams-tuned skill package active. The installer
uses symlinks by default and can copy with `--copy`.
