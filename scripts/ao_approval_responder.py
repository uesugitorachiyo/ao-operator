#!/usr/bin/env python3
"""F-B: deterministic AO approval responder for autonomous secure-agent runs.

Wraps `ao-policy pending|approve|deny` in a polling loop so the secure-agent
profile's policy-gated actions can be exercised end-to-end without a human
in the loop. Designed to satisfy the "real approval cycle observation"
requirement of V3 (`run-artifacts/release-v0.1.1/PLAN.md` closure criterion).

Decision rule (deterministic, default-fail-closed):

  For each pending ticket:
    if (ticket.action_type, command_prefix) matches an explicit --allow rule
      -> approve via `ao-policy approve <id>`
    else
      -> deny via `ao-policy deny <id>` with reason
         "responder default-deny: not on operator allowlist"

The reason and decided_by trail land in the SQLite ticket row, which the
secure-agent profile's `policy-auditor` role reads back as the verdict
table for its `compliance-report.md`.

Stops when:
  - SIGINT (Ctrl-C) received; outstanding tickets are not auto-decided
  - the pending queue is empty for `--max-idle-polls` consecutive polls
    (default 5) — interpreted as "the run is done, no more requests will
    arrive."

Usage:
  python3 scripts/ao_approval_responder.py \\
      --db /tmp/ao-secagent-XXX/approvals.db \\
      --ao-policy /path/to/ao-runtime/target/debug/ao-policy \\
      --allow shell.run:mv \\
      --allow shell.run:cp \\
      --max-idle-polls 5 --poll-interval 1.0

Run alongside `factory_run.py --profile secure-agent --run --ao-home <dir>`;
the responder uses the same .ao/approvals.db that AO writes when a task
hits a `decision: ask` rule.

Exit codes:
  0  responder shut down cleanly (idle quota reached or SIGINT)
  1  responder usage error or ao-policy binary not executable
  2  unrecoverable error mid-run (a sub-call to ao-policy failed)
"""
from __future__ import annotations

import argparse
import json
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AllowRule:
    action_type: str
    command_prefix: str | None  # None means "any command"

    @classmethod
    def parse(cls, spec: str) -> "AllowRule":
        """Parse `action_type` or `action_type:prefix` into an AllowRule."""
        if ":" in spec:
            kind, prefix = spec.split(":", 1)
            return cls(kind.strip(), prefix.strip() or None)
        return cls(spec.strip(), None)


def _matches(rule: AllowRule, ticket: dict) -> bool:
    if ticket.get("action_type") != rule.action_type:
        return False
    if rule.command_prefix is None:
        return True
    cmd = ticket.get("action_command") or ""
    return cmd == rule.command_prefix or cmd.startswith(rule.command_prefix + " ")


def _decide(ticket: dict, allows: list[AllowRule]) -> tuple[str, str]:
    """Return (verb, reason) for a ticket. verb is "approve" or "deny"."""
    for rule in allows:
        if _matches(rule, ticket):
            prefix = rule.command_prefix or "<any>"
            return "approve", (
                f"responder allow rule matched: {rule.action_type}:{prefix}"
            )
    return "deny", "responder default-deny: not on operator allowlist"


def _ao_pending(ao_policy: Path, db: Path) -> list[dict]:
    proc = subprocess.run(
        [str(ao_policy), "--db", str(db), "pending", "--json"],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"ao-policy pending failed (code {proc.returncode}): {proc.stderr.strip()}"
        )
    return json.loads(proc.stdout) if proc.stdout.strip() else []


def _ao_decide(ao_policy: Path, db: Path, verb: str, ticket_id: str, reason: str) -> None:
    proc = subprocess.run(
        [str(ao_policy), "--db", str(db), verb, ticket_id, "--reason", reason],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"ao-policy {verb} {ticket_id} failed (code {proc.returncode}): "
            f"{proc.stderr.strip()}"
        )


_INTERRUPTED = False


def _on_sigint(_signum, _frame) -> None:  # pragma: no cover - signal handler
    global _INTERRUPTED
    _INTERRUPTED = True


def run_responder(
    *,
    ao_policy: Path,
    db: Path,
    allows: list[AllowRule],
    max_idle_polls: int,
    poll_interval: float,
    emit_json: bool,
    out=sys.stdout,
) -> dict[str, int]:
    """Main responder loop. Returns counts dict (approved, denied, idle_polls)."""
    counts = {"approved": 0, "denied": 0, "polls": 0, "tickets_seen": 0}
    idle = 0
    seen: set[str] = set()
    while not _INTERRUPTED:
        counts["polls"] += 1
        try:
            pending = _ao_pending(ao_policy, db)
        except RuntimeError as exc:
            print(f"ao_approval_responder: {exc}", file=sys.stderr)
            return counts
        if not pending:
            idle += 1
            if idle >= max_idle_polls:
                break
            time.sleep(poll_interval)
            continue
        idle = 0
        for ticket in pending:
            tid = ticket["id"]
            if tid in seen:
                continue
            seen.add(tid)
            counts["tickets_seen"] += 1
            verb, reason = _decide(ticket, allows)
            try:
                _ao_decide(ao_policy, db, verb, tid, reason)
            except RuntimeError as exc:
                print(f"ao_approval_responder: {exc}", file=sys.stderr)
                return counts
            counts["approved" if verb == "approve" else "denied"] += 1
            event = {
                "ticket_id": tid,
                "action_type": ticket.get("action_type"),
                "action_command": ticket.get("action_command"),
                "decision": verb,
                "reason": reason,
            }
            print(json.dumps(event) if emit_json else
                  f"{verb}\t{tid}\t{ticket.get('action_type')}\t"
                  f"{ticket.get('action_command') or ''}\t{reason}",
                  file=out, flush=True)
        time.sleep(poll_interval)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic AO approval responder for autonomous secure-agent smokes."
    )
    parser.add_argument("--db", required=True, type=Path,
                        help="Path to AO approval-queue SQLite database (matches ao-policy --db).")
    parser.add_argument("--ao-policy", default="ao-policy", type=Path,
                        help="Path to the ao-policy binary (default: PATH lookup).")
    parser.add_argument("--allow", action="append", default=[],
                        metavar="ACTION_TYPE[:COMMAND_PREFIX]",
                        help="Approve any pending ticket matching this rule. "
                             "Repeat for multiple rules. Examples: "
                             "'shell.run:mv', 'agent.run.codex'.")
    parser.add_argument("--max-idle-polls", type=int, default=5,
                        help="Stop after this many consecutive empty-queue polls (default: 5).")
    parser.add_argument("--poll-interval", type=float, default=1.0,
                        help="Seconds between polls (default: 1.0).")
    parser.add_argument("--json", action="store_true",
                        help="Emit one JSON object per decision instead of TSV.")
    args = parser.parse_args(argv)

    ao_policy = args.ao_policy
    if not ao_policy.is_file() and shutil.which(str(ao_policy)) is None:
        print(f"ao_approval_responder: ao-policy binary not found: {ao_policy}", file=sys.stderr)
        return 1
    allows = [AllowRule.parse(spec) for spec in args.allow]

    signal.signal(signal.SIGINT, _on_sigint)
    counts = run_responder(
        ao_policy=ao_policy,
        db=args.db,
        allows=allows,
        max_idle_polls=args.max_idle_polls,
        poll_interval=args.poll_interval,
        emit_json=args.json,
    )
    summary = {"summary": True, **counts}
    print(json.dumps(summary) if args.json else
          f"summary\tpolls={counts['polls']}\ttickets={counts['tickets_seen']}\t"
          f"approved={counts['approved']}\tdenied={counts['denied']}",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
