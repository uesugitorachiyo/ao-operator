# Ports And Startup

Default provider ports:

- Claude factory: `127.0.0.1:8793`
- Codex factory: `127.0.0.1:8795`

Do not bind to public interfaces. If a port is occupied, use the repo's
`MISSION_MONITOR_PORT` override or stop the stale process.

Claude startup from `claude-agent-teams-v2`:

```bash
bash mission-monitor/start.sh
```

Codex startup from `codex-agent-teams-v2`:

```bash
bash start.sh
```

When shared monitor wrappers are involved, pass provider and port explicitly so
Claude and Codex monitors can run at the same time.
