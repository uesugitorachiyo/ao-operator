# Refactor Missing Pinning Brief

Use AO Operator to refactor the project service without changing observable
behavior.

This intentionally omits the required behavior lock so the refactor shape gate
must block before any mutator dispatch.
