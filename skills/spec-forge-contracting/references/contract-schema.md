# Contract Schema

Do not treat the contract as documentation after the fact. It is the source of
truth for emitted factory artifacts.

Each contract must include:

- `shape` and `classification`,
- problem and success criteria,
- negative constraints and out-of-scope items,
- readiness score and verdict,
- EARS/RFC-2119 `shall_statements`,
- acceptance criteria with verification oracles,
- sensitive fields and trigger hints,
- slices with `reads`, `writes`, `depends_on`, acceptance, and verification,
- optional knowledge-lookup note listing wiki pages consulted and the lesson
  applied, if lookup changed the contract.

## Acceptance Criteria

Each AC needs:

- `id`,
- concise behavior text,
- `shall_refs`,
- `oracle`,
- exact `verification`,
- file hints,
- risk tags.

If an AC cannot be verified, the contract is not ready.
