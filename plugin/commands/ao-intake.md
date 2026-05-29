---
description: Drive Shape-aware AO Operator intake to turn raw intent into a dispatch-ready brief.
argument-hint: <raw intent>
---

# /ao-intake — Shape-aware intake

Turn the raw intent in `$ARGUMENTS` into a classified, dispatch-ready AO Operator
brief before any code is touched.

1. Invoke the **factory-intake** skill (it is installed by this plugin) and
   follow it: classify the work, assign a Shape, declare slices, scoped reads,
   scoped writes, sensitive fields, and explicit verification.
2. Produce a brief markdown suitable for `/ao-render` and `/ao-run`.
3. Stop at the intake contract — do not implement. Hand the brief to `/ao-render`
   to preview the factory, then `/ao-run` to execute.
