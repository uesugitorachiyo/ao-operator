# 39 - Security Threat Model And Data-Flow

Classification: COMPLEX
Shape: greenfield

## Scope

This slice records the STRIDE threat model and data-flow for AO Operator before
public release or wider remote-worker exposure. It is a no-provider
documentation and verification lane; it does not authorize live dispatch.

## Data-Flow

The security data-flow is:

```text
operator
  -> AO Operator CLI and operator slices
  -> AO Runtime runspec, policy, and event stream
  -> remote worker transfer staging and workspace bundle
  -> provider CLI on the worker
  -> role artifacts, AO events, reports, and returned evidence
  -> evaluator and release readiness gates
```

## Trust Boundaries

- Operator approval boundary: live provider, remote DAST, and manual pen-test
  actions must remain behind explicit approval gates.
- SSH transport boundary: Mac-to-Ubuntu transfer requires pinned host identity,
  known_hosts evidence, and no opportunistic host-key trust.
- AO event artifacts boundary: AO events and role artifacts are durable
  evidence, but they must be redacted before public release.
- OAuth credential boundary: provider OAuth files and CLI session state remain
  local to the provider machine and are never bundled, transferred, or
  committed.
- Workspace bundle boundary: archives must be size-bounded and extracted with
  safe archive extraction that rejects traversal, links, special files, and
  escaping paths.

## Assets

- provider OAuth credentials and provider CLI session material
- workspace bundle and chunk manifests
- AO events, role artifacts, operator reports, and release evidence
- operator approval state and manual exception records
- remote worker identity, SSH key material, and known_hosts state

## STRIDE Threats

- Spoofing: remote worker identity, SSH host identity, or provider CLI identity
  could be impersonated.
- Tampering: workspace bundles, chunks, manifests, or returned artifacts could
  be modified before evaluation.
- Repudiation: live run or manual pen-test actions could lack durable operator
  approval and cleanup evidence.
- Information disclosure: provider OAuth paths, bearer-token-shaped text,
  private machine paths, private network targets, or stale context markers
  could leak through AO events or committed artifacts.
- Denial of service: large prompt/status fanout, unbounded archive extraction,
  or oversized returned artifacts could stall workers or fill disk.
- Elevation of privilege: malformed bundles, symlinks, path traversal, or
  approval bypass could cause writes outside the intended staging path or start
  unauthorized live provider work.

## Mitigations

- Host-key pinning and known_hosts evidence for remote transfer.
- Safe archive extraction with traversal, link, special-file, count, and size
  checks.
- Public-release scanner and strict-public HIGH gate for committed artifacts.
- No-provider DAST as the default dynamic test lane.
- Manual pen test gate for adversarial remote testing after explicit approval.
- Redaction for provider credentials, token-shaped values, private paths,
  private network targets, and stale context artifacts.
- Release readiness and artifact hygiene gates before closure.

## Verification

```bash
python3 scripts/check_security_threat_model.py --write-output --json
python3 scripts/check_public_release_security.py --strict-public --fail-on HIGH --json
```

## Acceptance Criteria

- STRIDE categories are documented.
- Data-flow from operator through AO Operator, AO Runtime, remote worker,
  provider CLI, and returned evidence is documented.
- Trust boundary, assets, threats, and mitigations are documented.
- `dispatch_authorized=false`.
- `live_providers_run=false`.
