# Read-Only Contract

`mission-monitor` observes repo files and live artifacts. It must not mutate:

- specs,
- plans,
- status logs,
- evaluations,
- contracts,
- git state,
- worker state,
- provider auth or session state.

The monitor reports lifecycle state; it does not own worker lifecycle. Provider
adapters should normalize discovery and state projection without unkeyed global
mutable state.

Do not weaken `/api/file` allowlists when adding visibility. Add explicit safe
paths or derived read-only views instead.
