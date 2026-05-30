#!/usr/bin/env bash
#
# Drive `ao2 sdd plan --provider claude` against a fresh /tmp/dogfood-target
# using the persisted claude shim (OAuth path, no ANTHROPIC_API_KEY).
#
# Usage:
#   ./dogfood.sh "<prompt text>"
#   ./dogfood.sh           # uses the default prompt
#
# Artifacts:
#   /tmp/dogfood-plan.json                    — canonical plan
#   /tmp/dogfood-target/target/sdd-planner/*  — per-attempt orchestrator logs
#   /tmp/sdd-planner-claude-shim/logs/*       — per-invocation shim logs

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AO2_REPO="${AO2_REPO:-[AO2_REPO]}"
SDD_PLANNER_REPO="${SDD_PLANNER_REPO:-$AO2_REPO}"
AO2_BIN="${AO2_BIN:-$AO2_REPO/target/debug/ao2}"
TARGET_DIR="${TARGET_DIR:-/tmp/dogfood-target}"
OUT_PATH="${OUT_PATH:-/tmp/dogfood-plan.json}"

DEFAULT_PROMPT='Add a Rust function `farewell() -> &'"'"'static str` to src/lib.rs that returns "bye" and add a test for it. Keep the change minimal and idiomatic.'
PROMPT="${1:-$DEFAULT_PROMPT}"

echo ">>> Recreating $TARGET_DIR from tiny-repo fixture"
rm -rf "$TARGET_DIR"
cp -R "$SDD_PLANNER_REPO/crates/sdd-planner/tests/fixtures/tiny-repo" "$TARGET_DIR"
(
  cd "$TARGET_DIR"
  git init -q
  git add -A
  GIT_AUTHOR_NAME=dogfood GIT_AUTHOR_EMAIL=dogfood@local \
  GIT_COMMITTER_NAME=dogfood GIT_COMMITTER_EMAIL=dogfood@local \
    git commit -q -m "initial tiny-repo snapshot"
)

if [[ ! -x "$AO2_BIN" ]]; then
  echo ">>> Building ao2-cli (debug)"
  cargo build -p ao2-cli --manifest-path "$AO2_REPO/Cargo.toml"
fi

echo ">>> Clearing prior shim logs"
rm -rf /tmp/sdd-planner-claude-shim/logs
mkdir -p /tmp/sdd-planner-claude-shim/logs

rm -f "$OUT_PATH"

echo ">>> Running ao2 sdd plan --provider claude"
echo "    prompt: $PROMPT"
PATH="$SCRIPT_DIR:$PATH" "$AO2_BIN" sdd plan \
  --prompt "$PROMPT" \
  --target "$TARGET_DIR" \
  --provider claude \
  --out "$OUT_PATH"

echo
echo ">>> Plan written to $OUT_PATH"
echo ">>> Validating"
"$AO2_BIN" sdd validate --plan "$OUT_PATH" || true

echo
echo ">>> Shim logs"
ls -la /tmp/sdd-planner-claude-shim/logs/
