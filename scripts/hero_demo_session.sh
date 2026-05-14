#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

run_step() {
  printf '\n$ %s\n' "$*"
  sleep 0.9
  "$@"
  sleep 3.2
}

printf 'AO Operator\n'
printf 'local autonomous agent CLI for Codex and Claude Code subscriptions\n'
sleep 2.0

run_step python3 scripts/factory_run.py --list-profiles

run_step python3 scripts/factory_run.py tasks hero-bug-fix --profile bug-fix --json

run_step python3 scripts/factory_run.py \
  --brief examples/starters/bug-fix-example.md \
  --profile bug-fix \
  --slug hero-bug-fix \
  --dry-run \
  --overwrite-artifacts

run_step python3 scripts/runspec_export.py \
  --slug hero-bug-fix \
  --profile bug-fix \
  --brief examples/starters/bug-fix-example.md \
  --output-path /tmp/ao-operator-hero/bug-fix \
  --json

run_step python3 scripts/runspec_import.py \
  /tmp/ao-operator-hero/bug-fix.factory/runspec.yaml \
  --json

printf '\nAO Operator: roles instead of one-off chats, artifacts instead of lost context.\n'
sleep 10.0
