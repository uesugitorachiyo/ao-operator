# Hermes Governed Backend Boundary

The product direction is:

- Hermes is the front end, queue, cron trigger, and memory bookkeeping surface.
- AO Operator / AO Operator owns contracts, profiles, role discipline, evaluator closure, and governed workflow execution.
- AO2 owns trusted execution, memory, replay, and signed evidence boundaries.
- AO2 Control Plane is a read-only observer for signed evidence and memory exports.

Hermes must not become the trusted backend executor. For development and
overnight automation, Hermes should launch bounded Factory/AO2 workflows, inspect
their artifacts, and record memory. It should not directly mutate AO artifacts or
bypass Factory evaluator/closer.

Acceptable Hermes cron work:

- Run `scripts/hermes_nightly_ao2_advancement.py` and inspect its generated artifacts.
- Run `scripts/hermes_ao_bridge.py` commands that preserve the Factory/AO2 trust boundary.
- Read AO2 Control Plane release posture through `scripts/hermes_ao_bridge.py
  release-cockpit-status`, which fetches `/api/v1/release/cockpit.json` with an
  environment token and emits a sanitized front-end status artifact including
  latest Codex/Claude provider acceptance status, source class, run ID, score,
  and raw observer evidence links.
- Read AO2 Control Plane release-candidate handoff posture through
  `scripts/hermes_ao_bridge.py release-handoff-status`, which fetches
  `/api/v1/release/handoff.json` and emits only sanitized front-end fields and
  links to the read-only `/api/v1/release/handoff` operator panel for Factory
  evaluator/closer review. Hermes may display this handoff, but it must not
  treat it as approval authority.
- Read AO2 Control Plane release-readiness posture through
  `scripts/hermes_ao_bridge.py release-readiness-status`, which fetches
  `/api/v1/release/readiness.json` and emits compact gate, blocker, and
  evaluator/closer ownership fields for Hermes UI/cron. Hermes may display the
  readiness verdict, but Factory evaluator/closer remains the release
  acceptance owner.
- Write memory checkpoints from governed artifacts.
- Report blockers when the governed path cannot execute.

Unacceptable Hermes cron work:

- Direct arbitrary repo mutation without a Factory/AO2 governed workflow.
- Bypassing evaluator/closer.
- Writing AO artifacts by hand when a repo script owns that mutation.
- Introducing API-key provider auth instead of local OAuth CLI auth.
- Exposing bearer tokens in logs, URLs, reports, markdown, or generated artifacts.

This boundary exists so Hermes can be a useful operator surface while AO2 and
Factory remain the trusted execution and evidence system.
