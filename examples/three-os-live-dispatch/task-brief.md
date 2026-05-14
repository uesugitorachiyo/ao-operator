# Three-OS Live Dispatch Release Gate

Scope: produce a operator release-gate evidence run that proves AO Operator can
use AO Runtime to dispatch Codex-backed work across macOS, Ubuntu, and native
Windows workers.

Build no product feature patch in this run. Prove AO Operator can route Codex-backed work through AO Runtime to three native
worker lanes:

- macOS worker tagged `mac,live`
- Ubuntu worker tagged `ubuntu`
- native Windows worker tagged `windows,live`

The output must be release-gate evidence, not a product feature patch. Each role
must write only its declared artifact, include non-sensitive OS evidence, and
avoid hostnames, private IP addresses, auth paths, provider secrets, and full
provider transcripts.

Acceptance:

- All three worker roles return `DONE` or `DONE_WITH_CONCERNS`.
- The final evaluator returns `DONE` or `DONE_WITH_CONCERNS`.
- AO events show remote coordinator dispatch through host-tagged nodes.
- Provider API-key environment variables are absent from the proof.
- The proof remains private until explicit public-launch approval.
