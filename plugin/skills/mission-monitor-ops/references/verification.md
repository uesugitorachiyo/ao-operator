# Verification

Use stdlib unit tests from the target factory repo:

```bash
python3 -m unittest discover mission-monitor/tests -v
```

If dashboard state changed, also run the factory self-check when present:

```bash
python3 scripts/self_check.py --fast --json
```

For shared monitor or provider-adapter changes, start both monitors
concurrently and verify both providers:

```bash
curl -fsS http://127.0.0.1:8793/api/health
curl -fsS http://127.0.0.1:8793/api/state
curl -fsS http://127.0.0.1:8795/api/health
curl -fsS http://127.0.0.1:8795/api/state
```

Gate R tests for monitor refactors should prove concurrent Claude and Codex
startup, provider-scoped discovery, correct default ports, and no API-key
requirements.
