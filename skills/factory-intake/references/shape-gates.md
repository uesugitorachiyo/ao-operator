# Shape Gates

`Shape` determines the pre-mutation gate. Do not downgrade a task shape to avoid
these checks.

## Bug-Fix: Gate B

For `Shape: bug-fix`, intake must include:

- failing reproducer on HEAD,
- top-3 suspect ranking with reasons,
- WHAT/WHY/blast-radius,
- red -> fix -> green closure command.

The `BUG-FIX:TRIVIAL` escape hatch is only for tiny, one-file fixes where the
reproducer and fix are obvious and verification is still deterministic.

## Refactor: Gate R

For `Shape: refactor`, intake must include:

- pinning suite green on HEAD,
- atomic slice plan and rollback for each slice,
- expected-diff allowlist,
- pinning-suite-green-at-every-step closure.

Refactors must preserve behavior unless the user explicitly authorizes a
behavior change.

## Greenfield

For `Shape: greenfield`, intake must state expected behavior, acceptance
criteria, integration points, and tests or smoke checks that prove the feature
exists.
