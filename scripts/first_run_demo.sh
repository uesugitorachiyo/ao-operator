#!/usr/bin/env bash
set -euo pipefail

slug="${1:-agent-team-demo-first-run}"
profile="${2:-bug-fix}"
brief="examples/agent-team-demo/task-brief.md"

if [[ ! -f "$brief" ]]; then
  echo "Run this script from the AO Operator repository root." >&2
  exit 1
fi

echo "AO Operator first-run demo"
echo "brief:   $brief"
echo "profile: $profile"
echo "slug:    $slug"
echo

echo "1. Show the role graph before materializing artifacts"
python3 scripts/factory_run.py tasks "$slug" --profile "$profile" --json || true
echo

echo "2. Materialize the dry-run operator package"
python3 scripts/factory_run.py specify "$brief" \
  --slug "$slug" \
  --profile "$profile" \
  --overwrite-artifacts
echo

echo "3. Show the role graph after the package exists"
python3 scripts/factory_run.py tasks "$slug" --profile "$profile" --json
echo

echo "4. Generated artifacts"
for path in \
  "run-artifacts/$slug" \
  "run-artifacts/$slug/$slug-status.md" \
  "run-artifacts/$slug/$slug.runspec.yaml" \
  "docs/specs/$slug-spec.md" \
  "docs/plans/$slug-plan.md"; do
  if [[ -e "$path" ]]; then
    echo "  - $path"
  else
    echo "  - MISSING: $path" >&2
    exit 1
  fi
done
echo

echo "Next: inspect run-artifacts/$slug/ and rerun with --run only after local Codex or Claude CLI auth is ready."
echo "The evaluator artifact is produced by live closure flows, not this provider-free dry run."
