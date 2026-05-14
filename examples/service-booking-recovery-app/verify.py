#!/usr/bin/env python3
"""Verify the service booking recovery app fixture."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SEED = ROOT / "data" / "seed-requests.json"
REQUIRED_STATUSES = {"new", "follow-up", "scheduled", "lost"}
REQUIRED_UI_MARKERS = [
    "Turn open requests into booked work today.",
    "Capture request",
    "Customer name",
    "Requested window",
    "Recovery board",
    "Next action",
    "saveable revenue",
    "Demo only: no SMS, email, payment, CRM, or phone-provider integration runs.",
]
REQUIRED_APP_MARKERS = [
    "function buildNextAction(request)",
    "function addRequest(event)",
    "new FormData(form)",
    "for (const status of statusOrder)",
    'column.className = "column"',
    'addEventListener("submit", addRequest)',
]


def main() -> int:
    requests = json.loads(SEED.read_text(encoding="utf-8"))
    statuses = {request["status"] for request in requests}
    missing = REQUIRED_STATUSES - statuses
    if missing:
        raise SystemExit(f"missing statuses: {sorted(missing)}")
    if len(requests) != 7:
        raise SystemExit(f"expected 7 requests, got {len(requests)}")
    saveable = sum(
        int(request["estimate"])
        for request in requests
        if request["status"] != "lost"
    )
    if saveable != 13400:
        raise SystemExit(f"unexpected saveable revenue: {saveable}")
    index = (ROOT / "index.html").read_text(encoding="utf-8")
    for marker in REQUIRED_UI_MARKERS:
        if marker not in index:
            raise SystemExit(f"missing UI marker: {marker}")
    app = (ROOT / "app.js").read_text(encoding="utf-8")
    for marker in REQUIRED_APP_MARKERS:
        if marker not in app:
            raise SystemExit(f"missing app marker: {marker}")
    print("verdict=PASS")
    print(f"request_count={len(requests)}")
    print(f"statuses={','.join(sorted(statuses))}")
    print(f"saveable_revenue={saveable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
