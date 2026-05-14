# Contributing to AO Operator

> Formal name: **AO Runtime Operator**. GitHub repo slug: `ao-operator`.
> Legacy compatibility slug: `ao-operator`.
> Formerly "Plain Factory".

AO Operator is the auditable agent-workflow operator you can run on your own
hardware. The public project is aimed at small businesses, agencies, solo
consultants, and local-first builders who need reproducible AI work without
turning the project into an enterprise compliance platform.

## Scope

Good contributions make the local operator clearer, easier to run, easier to
debug, or easier to trust. The project is opinionated but extensible: profiles,
skills, prompts, gates, and evidence artifacts should stay understandable before
they become configurable.

We are not currently accepting feature requests for enterprise compliance, SOC2
templates, HIPAA-specific fixtures, managed enterprise execution, or a broad
multi-provider router.

## Filing Issues

Before opening an issue, search existing issues and check the latest README and
setup notes. Bug reports should include what you were trying to do, what broke,
the command you ran, the profile or brief involved, and any redacted logs needed
to reproduce the behavior.

Feature requests should explain the small-biz workflow they improve. A concrete
brief, profile, or artifact example is more useful than a broad platform idea.

## Development Setup

Use a local checkout and local provider CLI auth. API-key based provider auth is
not part of the supported development path.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
pytest
```

Provider CLIs such as Codex and Claude must use their local OAuth/subscription
login flows. Do not add `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or provider API
key paths to examples, tests, or docs.

## Test Convention

Use `pytest` for Python tests. Narrow changes should include targeted tests next
to the behavior they touch. Shared behavior, profile loading, RunSpec rendering,
artifact hygiene, and gate behavior need regression coverage.

Useful commands:

```sh
pytest tests/test_factory_run_gates.py -q
pytest -k factory_run
python3 scripts/validate_factory.py
```

When a change affects launch or release hygiene, run the relevant readiness or
validation script and report the result in the PR.

## Pull Requests

Keep PRs small enough to review. Include:

- A short statement of the user-facing behavior change
- The tests or checks you ran
- Any profile, prompt, or artifact compatibility notes
- Any sensitive fields touched and how they are redacted

Do not rewrite unrelated files, refresh generated artifacts without explaining
why, or mix public launch work with private environment cleanup.

## Profiles And Artifacts

Profiles are public contracts. Preserve default behavior unless the PR states a
migration path. AO artifacts are the handoff boundary between roles, so changes
to reads, writes, gates, or evidence paths need explicit tests.

## Code Of Conduct

By participating, you agree to follow the Code of Conduct in
`CODE_OF_CONDUCT.md`.

## CLA

AO Operator does not currently require a Contributor License Agreement.
Contributions are accepted under the repository license.
