# Model Routing

Use the least capable model that can safely complete the delegated work.

## Tiers

- Cheap or fast model: file maps, grep summaries, doc inventory, simple lint,
  and mechanical verification.
- Standard model: routine implementation, tests, docs, and bounded bug fixes.
- Strong model: architecture, ambiguous failures, security boundaries,
  multi-repo tradeoffs, and hard refactors.

## Parallelism

Parallelize only truly independent work:

- disjoint read questions,
- disjoint write sets,
- verifier work that can run while implementation continues,
- specialist reviews that inspect different concerns.

Do not duplicate the same unresolved task across agents. If two agents may edit
the same files, split ownership first or keep the work local.

After a subagent finishes, review changed paths and integrate only the relevant
result. Close idle agents when their result is no longer needed.
