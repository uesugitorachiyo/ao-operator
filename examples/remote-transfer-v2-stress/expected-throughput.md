# Expected Throughput

The stress topology is a dry-run lane, so throughput is measured by generated
AO Operator artifacts rather than live provider completions.

- Total AO tasks: 2007
- Parallel implementation factories after `factory-manager`: 1000
- Parallel reviewers after implementation: 1000
- Required generated prompts: 2007
- Live provider calls by default: 0
- Topology validator probe: 50007 AO tasks from 25000 slices
- Count-only ceiling probe: 200007 AO tasks from 100000 slices
- Ceiling probe generated prompts: 0

Passing validation means AO Operator can materialize, index, and validate the
large topology without dispatching live provider work.
