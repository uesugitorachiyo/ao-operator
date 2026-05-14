# Bug Fix Example

The test `tests/test_invoice_totals.py::test_rounds_tax_to_cents` is flaky
because tax rounding sometimes uses binary floating point. Reproduce the
failure, replace the calculation with decimal arithmetic, and add a regression
assertion that proves cents are stable.
