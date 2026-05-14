# Bounded Live Expected Throughput

This is the provider-safe live profile for Remote Transfer v2 stress work.
It is intentionally much smaller than the 1000-slice dry-run topology.

- Total AO tasks: 107
- Live implementation factories after `factory-manager`: 50
- Live reviewers after implementation: 50
- Required generated prompts: 107
- Live provider calls are bounded to the generated topology size.
- Escalate to 25 pairs only after this profile completes without provider
  limit, auth, network, or closure blockers.

The 1000-slice topology remains the materialization-only stress lane.
