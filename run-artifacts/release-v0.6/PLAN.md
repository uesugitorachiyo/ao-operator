# AO Operator v0.6 - Public OSS Launch Prep

> **Status:** Launch-prep candidate tagged as `v0.6.0`; operator-only public
> submission and naming actions remain.
> **Public name:** AO Operator.
> **Repository:** `factory-v3`, with public copy using the AO Operator name.
> **Safety posture:** local-first, OAuth CLI provider auth only, no provider API
> keys, no enterprise compliance pivot, and no public submission without
> operator sign-off.

---

## A - Goal

v0.6 prepares `factory-v3` for its first public OSS launch as AO Operator:
auditable agent workflows on your hardware.

The release should make it possible for a new user to answer five questions
from the public repo:

1. What is this project and who is it for?
2. How do I run a small starter workflow?
3. How are role chains represented as data?
4. What project governance and contribution rules apply?
5. What public launch assets are ready for review?

## B - Completed Scope

| # | Item | Evidence |
|---|------|----------|
| P0 | Launch strategy pushed to origin. | `a2314915` |
| P1 | Public naming decision resolved as AO Operator. | `docs/strategy/naming-decision.md`, `6f635929` |
| P2 | OSS governance files added. | `LICENSE`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `.github/`, `5cdbfd19` |
| P3 | Private release/security/live artifacts moved out of public repo. | private overlay checkout, `74e19308`, `294c0149` |
| P4 | Workflow-as-data export/import added. | `scripts/runspec_export.py`, `scripts/runspec_import.py`, `tests/test_runspec_export_import.py`, `8990c4cb` |
| P5 | Starter profiles, starter briefs, and Spec-Kit aliases added. | `profiles/starters/`, `examples/starters/`, `skills/spec-kit-aliases/`, `8bc691a5` |
| P6 | Hero demo assets and HN draft added. | `docs/assets/hero.*`, `docs/launch/hn-draft.md`, `1d48d29b`, `b0288871` |
| R1 | Public README refreshed. | `README.md`, `3d28f942` |
| R2 | Release notes for v0.6 added. | `docs/status/release-v0.6/RELEASE-NOTES.md`, `a3631c8c` |
| R3 | Clean-clone verification completed for the v0.6 candidate. | `docs/status/release-v0.6/RELEASE-NOTES.md` |
| R6 | v0.6.0 annotated tag created. | `v0.6.0` -> `eb58482a` |
| R7 | Post-`v0.6.0` docs folded into a follow-up release candidate after AO Runtime WAL/native-deploy coverage finished. | `docs/status/release-v0.6.1/RELEASE-NOTES.md` |

## C - Remaining Scope

| # | Item | Where | Status |
|---|------|-------|--------|
| R4 | Operator review of HN tone and launch timing. | `docs/launch/hn-draft.md` | operator-only |
| R5 | Domain and GitHub org claim. | Manual registrar/GitHub availability check for AO Operator naming. | operator-only |
| R8 | Future post-tag docs, if any, require a new clean-clone verification before another tag. | temporary clone, pytest, quickstart commands | conditional |

## D - Closure Criteria

| # | Criterion | Evidence |
|---|-----------|----------|
| V1 | README quickstart commands run as written. | Command transcript or verification notes in release notes. |
| V2 | Starter profile and alias tests pass. | `pytest -q tests/test_starter_profiles.py tests/test_spec_kit_aliases.py tests/test_runspec_export_import.py` |
| V3 | Full public test suite passes after private artifact extraction. | `pytest -q` |
| V4 | Hero assets are present and small enough for README/HN use. | `docs/assets/hero.gif`, `docs/assets/hero.mp4`, `ffprobe`/file-size output |
| V5 | Release notes summarize changes, verification, and known operator actions. | `docs/status/release-v0.6/RELEASE-NOTES.md` |

## E - Out Of Scope

- No enterprise compliance package.
- No SOC2 or HIPAA-specific templates.
- No multi-provider router.
- No hosted execution service.
- No public AO Runtime launch in this release.
- No HN, X, Reddit, or Product Hunt submission by an agent.
- No domain purchase or GitHub organization claim by an agent.

## F - Next Action

For public launch, the remaining actions are operator-owned: approve or edit the
HN draft, claim the chosen GitHub org/name and domains, then submit public posts
manually. Any future post-tag documentation release must repeat the clean-clone
verification before a new tag.
