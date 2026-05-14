# AI Agent Credential Reachability Gate

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that no untrusted source (user prompt, agent tool output,
MCP tool result, web fetch payload, prompt-injection-tainted
content) can reach a credential-bearing path (provider OAuth file,
signed-bundle private key, API key store, session token, ssh key
directory, env-resolved API key) without an explicit egress
redaction step. The gate is fail-closed against the five highest-
risk credential-reachability dataflow hazards: an untrusted user
prompt concatenated into a subprocess argv touching the credential
directory MUST be rejected; an agent tool output piped to a
git/scp/rsync shell pipeline targeting the ssh directory MUST be
rejected; an MCP tool result included verbatim in a role-handoff
state envelope that carries session token paths MUST be rejected;
a web-fetch payload reflected into a shell command resolving an env
variable carrying a credential MUST be rejected; and a prompt-
injection-tainted source triggering a filesystem read of a
credential path while the egress redaction step is bypassed MUST be
rejected.

## Contract

`scripts/check_ai_agent_credential_reachability.py` emits
`ao-operator/ai-agent-credential-reachability/v1`.

The gate runs six deterministic cases (one control PASS + five
mutations FAIL) against an in-process credential-reachability
dataflow state machine with fixed synthetic placeholder identifiers
(`.credentials/factory_alpha`, `.ssh/factory_alpha`,
`.session/token_alpha`, `FACTORY_PROVIDER_API_KEY_ALPHA`,
`.config/factory_alpha/credentials.json`,
`docs/public/welcome_alpha.md`). Each case persists a per-case
`credential-reachability-transcript.json` to a temporary work
directory and records `observed_verdict` next to
`expected_case_verdicts`.

Source classifications: `trusted_internal`, `untrusted_user_prompt`,
`untrusted_tool_output`, `untrusted_mcp_result`,
`untrusted_web_fetch`, `untrusted_prompt_injection`.

Sinks: `subprocess_argv`, `shell_pipe`, `role_handoff`,
`shell_env_resolved`, `filesystem_read`.

Cases:

- `clean_no_untrusted_to_credential_reachable_path` — control:
  every dataflow edge is either trusted-source, non-credential-
  reachable, or redacted at egress; the verifier produces no
  errors.
- `untrusted_user_prompt_subprocess_argv_touches_credential_dir_rejected`
  — mutation: an untrusted user prompt is concatenated into a
  subprocess argv that touches the credential directory; the
  verifier records
  `untrusted_user_prompt_subprocess_argv_credential_reachable`.
- `agent_tool_output_piped_to_shell_with_ssh_dir_rejected` —
  mutation: an agent tool output is piped to a git/scp/rsync shell
  pipeline targeting the ssh directory; the verifier records
  `untrusted_tool_output_shell_pipe_credential_reachable`.
- `mcp_tool_result_included_in_role_handoff_with_session_paths_rejected`
  — mutation: an MCP tool result is included verbatim in a role-
  handoff state envelope that carries session token paths; the
  verifier records
  `untrusted_mcp_result_role_handoff_credential_reachable`.
- `web_fetch_reflected_into_shell_resolving_env_rejected` —
  mutation: a web-fetch payload is reflected into a shell command
  that resolves an env variable carrying a credential; the verifier
  records `untrusted_web_fetch_shell_env_resolved_credential_reachable`.
- `prompt_injection_fs_read_of_credential_path_bypassing_redaction_rejected`
  — mutation: a prompt-injection-tainted source triggers a
  filesystem read of a credential path while the egress redaction
  step is bypassed; the verifier records
  `untrusted_prompt_injection_filesystem_read_credential_reachable`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not write inside the repo working tree.
- Do not introduce randomness — all cases are deterministic with
  fixed synthetic source/sink/target identifiers.
- Do not derive dataflow edges from real production credentials,
  OAuth files, ssh directories, session tokens, or env-resolved API
  keys.

## Verification

```bash
python3 -m pytest -q tests/test_check_ai_agent_credential_reachability.py
python3 scripts/check_ai_agent_credential_reachability.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/ai-agent-credential-reachability.json
```
