# Service Booking Recovery App Sample

This is a small working app produced from
[`examples/ingestible-specs/service-booking-recovery-sdd.md`](../ingestible-specs/service-booking-recovery-sdd.md).

It demonstrates the AO Operator promise in plain language: describe the outcome
you need, then get a visible app, seed data, and a verifier that proves the
important behavior.

## Run

```bash
cd examples/service-booking-recovery-app
python3 -m http.server 8766
```

Open `http://127.0.0.1:8766/`.

## Verify

```bash
python3 verify.py
```

Expected:

```text
verdict=PASS
request_count=7
statuses=follow-up,lost,new,scheduled
saveable_revenue=13400
```
