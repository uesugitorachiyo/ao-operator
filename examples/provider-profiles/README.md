# Provider Profiles

AO Operator does not require a fixed Claude+Codex combination. Provider choice
is runtime configuration.

Valid providers:

```text
codex
claude
```

Resolution order for each task:

1. Exact task id override, for example
   `FACTORY_V3_BACKEND_FACTORY_PROVIDER`.
2. Role-level override, for example `FACTORY_V3_IMPLEMENTER_PROVIDER`.
3. `FACTORY_V3_DEFAULT_PROVIDER`.
4. Topology `provider` field, when present.
5. Built-in default `codex`.

Profiles:

- `all-codex.env` - every role resolves to Codex.
- `all-claude.env` - every role resolves to Claude Code.
- `mixed-throughput.env` - example profile that uses Claude for critique and
  review gates, Codex for implementation-heavy branches.

The mixed profile is only a recommendation for one workload. It is not a hard
architecture rule.

Validate all bundled profiles with:

```bash
python3 scripts/validate_provider_profiles.py
```

`all-codex.env` is expected to render every core smoke role to `provider:
codex` and `agent: codex-default`.
