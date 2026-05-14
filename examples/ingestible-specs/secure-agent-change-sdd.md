# Secure Agent Change SDD: Block Secret Reads

## Goal

Demonstrate a secure coding-agent workflow where secret reads are explicitly
blocked before implementation.

## Threat Model

An agent may try to inspect files that look relevant but contain secrets. The
workflow should prove that the profile can classify and block those reads.

## Scope

- Identify paths matching `.env`, `secrets/`, or private key markers.
- Block direct reads of those paths.
- Allow reads of safe source files and tests.
- Emit policy evidence for the block decision.

## Non-Goals

- No real secret material.
- No deploy.
- No remote git write.
- No network access.

## Role Expectations

- Intake records the security boundary.
- Planner maps safe and unsafe file classes.
- Implementer works only in a copied workspace.
- Reviewer checks that blocked paths are named in policy evidence.
- Evaluator-closer rejects if the evidence is missing.

## Acceptance Criteria

- Secret-like paths are blocked.
- Safe fixture files remain readable.
- Policy evidence includes allow and block examples.
- Final report states that no source repo mutation occurred.
