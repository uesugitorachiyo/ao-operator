# Paste This Into Codex Or Claude Code: Service Booking App From SDD

Use this prompt when you want the first AO Operator trial to feel like a normal
business request. The requester describes the outcome, AO Operator turns the SDD
into a role graph and RunSpec, and Codex CLI or Claude Code can continue from
that structured handoff when live provider auth is available.

```text
You are in a parent directory where a new checkout can be created.

Goal:
- Use AO Operator to turn a plain-language service-booking request into a
  verified local app sample.
- Start from examples/ingestible-specs/service-booking-recovery-sdd.md.
- Keep the result outcome-focused: a small service business owner should see
  open requests, next actions, scheduled work, and saveable revenue.
- Do not set OPENAI_API_KEY or ANTHROPIC_API_KEY.
- Use local Codex CLI or Claude Code auth only if live execution is needed.
- Stop and report a blocker if git, Python 3, or provider CLI auth is missing.

Steps:
1. Clone https://github.com/uesugitorachiyo/ao-operator.git if it is not
   already present, then enter the repo.
2. Read examples/ingestible-specs/service-booking-recovery-sdd.md.
3. Verify the existing app fixture at examples/service-booking-recovery-app.
4. Ask AO Operator to ingest the SDD with the greenfield profile.
5. Inspect the generated role graph, RunSpec, status directory, spec, and plan.
6. If live provider execution is available, continue from the generated plan and
   improve the app sample while preserving:
   - local static HTML/CSS/JS;
   - synthetic seed booking requests;
   - visible request status groups;
   - next-action copy for each customer;
   - saveable revenue calculation;
   - verifier output that proves the important behavior.
7. If live provider execution is not available, stop after materialization and
   explain exactly what would run next.

Acceptance:
- Report the business outcome in one sentence.
- Report the fixture verification output.
- Report the role graph AO Operator created.
- Report the RunSpec path and status directory.
- Report the app artifacts created or the exact live-execution blocker.
- Report evidence, not just a summary.
```

Expected provider-free materialization:

```text
business outcome: recover service bookings from open requests
fixture verification: verdict=PASS, request_count=7, saveable_revenue=13400
profile loaded: greenfield
role graph: intake -> architect -> planner -> implementer -> reviewer -> evaluator-closer
runspec: run-artifacts/ingest-service-booking-recovery-sdd/ingest-service-booking-recovery-sdd.runspec.yaml
```

Why this is a strong first sample:

- It starts from language a non-technical owner could say.
- The SDD gives the agent enough intent to make better decisions without asking
  the user to design the implementation.
- AO Operator shows intake, planning, implementation, review, and closure as
  separate responsibilities.
- The output is visible and verifiable: an app folder, seed data, and a verifier.
