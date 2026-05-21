# AO Operator v0.6 Closure

Date: 2026-05-11

Status: `v0.6.0` launch-prep candidate is tagged and pushed. Current `main`
also carries post-tag documentation-only reconciliation for the private AO
Runtime validation lane.

## Release Summary

AO Operator v0.6 prepares `factory-v3` for public OSS launch. The release
changes the public front door from internal `factory-v3` lifecycle artifacts to a
small-biz/local-first product surface:

- AO Operator naming decision recorded.
- Public README refreshed with hero asset, quickstart, starter profiles, and
  workflow-as-data examples.
- OSS governance files added.
- Private release/security/live evidence extracted from the public repo.
- `.factory/runspec.yaml` export/import added.
- Starter profile library and example briefs added.
- Spec-Kit-style aliases added.
- Hero GIF/MP4/cast generated from a real terminal demo.
- HN draft added for operator review.

## Verification

Commands run on Ubuntu before the `v0.6.0` tag:

```bash
pytest -q
```

Result:

```text
1114 passed, 3 skipped
```

Focused launch tests:

```bash
pytest -q tests/test_starter_profiles.py tests/test_spec_kit_aliases.py tests/test_runspec_export_import.py
```

Result:

```text
14 passed
```

README quickstart commands were verified during release-note preparation:

```bash
python3 scripts/factory_run.py --list-profiles
python3 scripts/factory_run.py tasks demo-bug-fix --profile bug-fix --json
python3 scripts/factory_run.py specify examples/starters/bug-fix-example.md --slug demo-bug-fix --overwrite-artifacts
python3 scripts/runspec_export.py --slug demo-bug-fix --profile bug-fix --brief examples/starters/bug-fix-example.md --output-path /tmp/ao-operator-demo/bug-fix --json
python3 scripts/runspec_import.py /tmp/ao-operator-demo/bug-fix.factory/runspec.yaml --json
```

Hero assets:

```text
docs/assets/hero.gif  duration=32.83s  size=229104 bytes
docs/assets/hero.mp4  duration=24.86s  size=213429 bytes
docs/assets/hero.cast size=5.4K
```

## Boundaries

These remain out of scope for v0.6:

- No enterprise compliance package.
- No SOC2 or HIPAA-specific templates.
- No multi-provider router.
- No hosted execution service.
- No public AO Runtime launch.
- No HN, X, Reddit, or Product Hunt submission by an agent.
- No domain purchase or GitHub organization claim by an agent.

## Operator-Only Actions

- Check and register desired AO Operator domains manually.
- Claim GitHub organization/name targets manually after redirect impact is
  reviewed.
- Review and approve `docs/launch/hn-draft.md`.
- Submit public launch posts manually.

## Tag

Annotated tag:

```text
v0.6.0 -> eb58482a
```

Post-tag repo maintenance is conditional: if documentation commits after
`v0.6.0` are intentionally folded into a new public release, rerun clean-clone
verification from `origin/main` and cut a follow-up tag.
