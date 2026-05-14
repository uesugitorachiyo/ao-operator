# 37 - Public Release Security and DAST Gate

Classification: COMPLEX
Shape: greenfield

## Scope

This slice adds a public-release security gate and an SDLC DAST lane for Factory
v3. The public-release gate combines text scanning with Python AST checks for
high-risk implementation patterns. The DAST lane runs no-provider dynamic tests
against the remote transfer smoke and operator-slice execution surfaces.

The default DAST lane does not run live providers or remote dispatch. Remote
DAST requires a separate operator-controlled environment flag.

## Security Checks

- Public text and artifact scan for private keys, token-shaped values, API-key
  assignments, stale context markers, personal paths, and private network
  targets.
- Historical status/evaluation artifact redaction gate for local paths, private
  lab network targets, and stale context markers before strict-public scans.
- Status/evaluation JSON integrity gate to catch malformed evidence after
  redaction or report generation.
- Python AST scan for `subprocess` calls with `shell=True`.
- Python AST scan for unpinned SSH host-key policy.
- Python AST/text scan for shell tar extraction and unsafe `tarfile` extraction
  helpers.
- Dynamic no-provider tests for remote smoke bundle validation, SSH option
  posture, operator-slice execution, redaction, and the public-release scanner.

## Verification

```bash
python3 -m pytest -q tests/test_public_release_security.py tests/test_dast_readiness.py
python3 scripts/check_dast_readiness.py --write-output --json
python3 scripts/check_public_release_security.py --json
python3 scripts/redact_strict_public_artifacts.py --fail-on-changes --json
python3 scripts/check_status_json_integrity.py --json
python3 scripts/check_public_release_security.py --strict-public --summary-only --json
```

## Acceptance Criteria

- AST checks detect unsafe subprocess, tar extraction, and SSH trust posture.
- No-provider DAST passes without live providers.
- `dispatch_authorized=false`.
- `live_providers_run=false` unless `FACTORY_V3_DAST_REMOTE=1` is explicitly
  set for a separate remote run.
- Public-surface security reports remaining blockers instead of silently
  accepting personal paths or stale context artifacts.
- Strict-public mode includes committed status/evidence artifacts and emits a
  compact grouped report suitable for CI logs.
- Committed status/evaluation JSON artifacts remain parseable after redaction.
