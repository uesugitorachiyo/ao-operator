# Sandbox Egress Allowlist Gate

## Classification

- Size: MODERATE
- Shape: greenfield
- Dispatch posture: local only, no AO run, no provider dispatch

## Objective

Prove that no AO Operator agent sandbox egress attempt can reach
a host that is not on the operator allowlist and that no
IP-literal bypass, no DNS-rebind bypass, no proxy-chain bypass,
and no raw-socket bypass can be admitted as a side-channel
around the allowlist. The gate is fail-closed against the five
highest-risk sandbox egress bypass channels: an unallowlisted
host egress admit MUST be rejected; an IP-literal bypass admit
MUST be rejected; a DNS-rebind bypass admit MUST be rejected; a
proxy-chain bypass admit MUST be rejected; and a raw-socket
bypass admit MUST be rejected.

## Contract

`scripts/check_sandbox_egress_allowlist.py` emits
`ao-operator/sandbox-egress-allowlist/v1`.

The gate runs six deterministic cases (one control PASS + five
mutations FAIL) against an in-process sandbox egress allowlist
verifier with fixed synthetic placeholder identifiers
(`egress::allowlisted_alpha`, `egress::allowlisted_beta`,
`egress::allowlisted_gamma`,
`egress::unallowlisted_host_alpha`,
`egress::ip_literal_bypass_alpha`,
`egress::dns_rebind_bypass_alpha`,
`egress::proxy_chain_bypass_alpha`,
`egress::raw_socket_bypass_alpha`,
`host::operator_alpha`, `host::operator_beta`,
`host::operator_gamma`, `host::unallowlisted_alpha`,
`ip::literal_alpha`, `proxy::chain_alpha`,
`socket::raw_alpha`). Each case persists a per-case
`sandbox-egress-allowlist-transcript.json` to a temporary work
directory and records `observed_verdict` next to
`expected_case_verdicts`.

Egress classes: `allowlisted_egress`,
`unallowlisted_host_egress`, `ip_literal_bypass`,
`dns_rebind_bypass`, `proxy_chain_bypass`, `raw_socket_bypass`.

Approved egress classes: `allowlisted_egress`.

Hazard classes: `unallowlisted_host_egress_admit`,
`ip_literal_bypass_admit`, `dns_rebind_bypass_admit`,
`proxy_chain_bypass_admit`, `raw_socket_bypass_admit`.

Cases:

- `clean_no_unallowlisted_or_bypassed_egress_attempts` --
  control: every registered egress targets a host on the
  operator allowlist with no IP-literal bypass, no DNS-rebind
  bypass, no proxy-chain bypass, and no raw-socket bypass; the
  verifier produces no errors.
- `unallowlisted_host_egress_admitted_rejected` -- mutation: an
  egress targets a host that is not on the operator allowlist;
  the verifier records `unallowlisted_host_egress_admit_rejection`.
- `ip_literal_bypass_admits_unallowlisted_target_rejected` --
  mutation: an egress uses a literal IP address to bypass
  hostname-based allowlist checking and reach an unallowlisted
  target; the verifier records `ip_literal_bypass_admit_rejection`.
- `dns_rebind_bypass_admits_unallowlisted_target_rejected` --
  mutation: an egress relies on inconsistent DNS resolution
  between the allowlist check and the actual connection to
  bypass the allowlist; the verifier records
  `dns_rebind_bypass_admit_rejection`.
- `proxy_chain_bypass_admits_unallowlisted_target_rejected` --
  mutation: an egress is routed through a proxy chain that
  conceals an unallowlisted target host from the allowlist
  check; the verifier records `proxy_chain_bypass_admit_rejection`.
- `raw_socket_bypass_admits_unallowlisted_target_rejected` --
  mutation: an egress opens a raw socket to an unallowlisted
  target, bypassing the higher-layer allowlist check; the
  verifier records `raw_socket_bypass_admit_rejection`.

Overall verdict is PASS only when every observed verdict matches
the expected verdict and `dispatch_authorized=false` /
`live_providers_run=false`.

## Negative Constraints

- Do not run AO.
- Do not dispatch provider CLIs.
- Do not open any real network connection or invoke any
  production sandbox runtime, DNS resolver, proxy server, or
  raw socket -- the gate is a pure in-memory sandbox egress
  allowlist verifier with synthetic egress edges.
- Do not write inside the repo working tree.
- Do not introduce randomness -- all cases are deterministic
  with fixed synthetic egress / host / IP / proxy / socket
  identifiers.
- Do not derive egresses from real operator network logs, live
  allowlists, or wall-clock samples.

## Verification

```bash
python3 -m pytest -q tests/test_check_sandbox_egress_allowlist.py
python3 scripts/check_sandbox_egress_allowlist.py --write-output --json
```

## Evidence

The durable status artifact is:

```text
run-artifacts/remote-transfer-v2-stress-live/sandbox-egress-allowlist.json
```
