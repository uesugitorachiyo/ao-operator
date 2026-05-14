#!/usr/bin/env bash
set -euo pipefail

spec_path="${1:-examples/ingestible-specs/financial-citation-audit-sdd.md}"
profile="${2:-smoke-test}"
base="$(basename "$spec_path")"
base="${base%.*}"
safe_base="$(printf '%s' "$base" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9-' '-')"
slug="${3:-ingest-${safe_base%-}}"

if [[ ! -f "$spec_path" ]]; then
  echo "Spec not found: $spec_path" >&2
  echo "Try: examples/ingestible-specs/financial-citation-audit-sdd.md" >&2
  exit 1
fi

echo "AO Operator SDD ingestion demo"
echo "spec:    $spec_path"
echo "profile: $profile"
echo "slug:    $slug"
echo

echo "1. Convert the spec into a provider-free operator package"
python3 scripts/factory_run.py specify "$spec_path" \
  --slug "$slug" \
  --profile "$profile" \
  --overwrite-artifacts
echo

echo "2. Show the role graph"
python3 scripts/factory_run.py tasks "$slug" --profile "$profile" --json
echo

echo "3. Generated artifacts"
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

echo "Next: inspect run-artifacts/$slug/$slug.runspec.yaml, then run live only after local CLI auth is ready."
