# Release Artifact Index

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Create a durable index that links the current post-acceptance SDD lanes to their
status artifacts, so operators can see which documents and evidence files define
the current release posture.

## Contract

`scripts/check_release_artifact_index.py` emits
`ao-operator/release-artifact-index/v1`.

The index covers:

- `docs/sdd/62-remote-transfer-hardening-evidence-gate.md`
- `docs/sdd/37-public-release-security-and-dast.md`
- `docs/sdd/38-security-sdlc-roadmap.md`
- `docs/sdd/39-security-threat-model-data-flow.md`
- `docs/sdd/40-manual-penetration-test-gate.md`
- `docs/sdd/41-host-key-evidence-gate.md`
- `docs/sdd/42-manual-pentest-report-classifier.md`
- `docs/sdd/43-supply-chain-audit-gate.md`
- `docs/sdd/63-resource-performance-guardrails.md`
- `docs/sdd/64-agent-os-execution-approval-bundle.md`
- `docs/sdd/65-operator-guardrail-summary.md`
- `docs/sdd/66-agent-os-approval-materialization.md`
- `docs/sdd/67-release-artifact-index.md`
- `docs/sdd/68-agent-os-approval-lifecycle.md`
- `docs/sdd/69-agent-os-approved-launch-proof.md`
- `docs/sdd/70-agent-os-approval-cleanup.md`
- `docs/sdd/89-operator-safe-next-command.md`
- `docs/sdd/90-agent-os-runspec-dag-edge-coverage.md`
- `docs/sdd/91-agent-os-runspec-yaml-dag-parity.md`
- `docs/sdd/92-agent-os-runspec-yaml-semantic-parity.md`
- `docs/sdd/93-agent-os-runspec-yaml-schema-injection.md`
- `docs/sdd/94-agent-os-runspec-ao-preflight-compatibility.md`
- `docs/sdd/95-agent-os-router-default-state-version.md`
- `docs/sdd/96-agent-os-role-graph-backward-compat.md`
- `docs/sdd/97-remote-transfer-chunk-cleanup-invariants.md`
- `docs/sdd/98-remote-transfer-signed-bundle-tamper.md`
- `docs/sdd/99-remote-transfer-approval-expiry-rotation.md`
- `docs/sdd/100-remote-transfer-bundle-ordering-resume.md`
- `docs/sdd/101-remote-transfer-provider-redaction-round-trip.md`
- `docs/sdd/102-remote-transfer-network-retry-idempotency.md`
- `docs/sdd/103-remote-transfer-concurrent-transfer-collision.md`
- `docs/sdd/104-remote-transfer-bundle-schema-version-skew.md`
- `docs/sdd/105-remote-transfer-resource-exhaustion-guard.md`
- `docs/sdd/106-remote-transfer-clock-skew-tolerance.md`
- `docs/sdd/107-remote-transfer-bundle-id-uniqueness.md`
- `docs/sdd/108-remote-transfer-bundle-content-type-allowlist.md`
- `docs/sdd/109-remote-transfer-per-tenant-quota-isolation.md`
- `docs/sdd/110-remote-transfer-wire-encryption-required.md`
- `docs/sdd/111-remote-transfer-sender-identity-rotation.md`
- `docs/sdd/112-ai-agent-blast-radius-inventory.md`
- `docs/sdd/113-ai-agent-destructive-action-approval.md`
- `docs/sdd/114-ai-agent-credential-reachability.md`
- `docs/sdd/115-ai-agent-instruction-packaging-leak-detection.md`
- `docs/sdd/116-mcp-tool-poisoning-detection.md`
- `docs/sdd/117-deepsec-diff-review-advisory-sast.md`
- `docs/sdd/118-agent-supply-chain-integrity.md`
- `docs/sdd/119-prompt-injection-escape-boundary.md`
- `docs/sdd/120-approval-clock-skew-defense.md`
- `docs/sdd/121-agent-log-redaction-round-trip.md`
- `docs/sdd/122-per-tenant-blast-radius-cap.md`
- `docs/sdd/123-sandbox-egress-allowlist.md`
- `docs/sdd/124-agent-tool-arg-injection-escape.md`
- `docs/sdd/125-agent-output-canary-leak-detection.md`
- `docs/sdd/126-agent-os-execution-budget-enforcement.md`
- `docs/sdd/127-agent-system-prompt-tamper-detection.md`
- `docs/sdd/128-tool-result-cache-poisoning-defense.md`
- `docs/sdd/129-agent-credential-scope-narrowing.md`

The indexed status artifacts must all have `verdict=PASS`,
`dispatch_authorized=false`, and `live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not create approval files.
- Do not index failing status reports as release-ready.

## Verification

```bash
python3 -m pytest -q tests/test_check_release_artifact_index.py
python3 scripts/check_release_artifact_index.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/release-artifact-index.json
```
