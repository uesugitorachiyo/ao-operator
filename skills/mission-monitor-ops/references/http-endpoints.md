# HTTP Endpoints

Run checks against the relevant provider port:

```bash
curl -fsS http://127.0.0.1:<port>/api/health
curl -fsS http://127.0.0.1:<port>/api/state
```

For diagnostics-capable dashboards:

```bash
curl -fsS http://127.0.0.1:<port>/api/diagnostics
```

When supported, `/api/state` should expose provider context such as `provider`,
`port`, and `repo_root`. Transcript or session discovery should be
provider-scoped.

For stream and file endpoint changes, verify:

- stream responses do not require API keys,
- `/api/file` remains allowlisted,
- file reads stay inside intended repo artifact paths,
- provider-specific transcripts do not bleed into the other monitor.
