# Wiki Boundary

`llm-wiki` is an external knowledge repository. Treat it as read-only background
only when the user explicitly asks for lookup.

Do not:

- copy wiki pages into factory repos,
- make factory tests depend on the external wiki,
- cite `raw/` or `distilled/` directly from factory artifacts,
- block factory work when the wiki is absent in a fresh clone,
- create or update factory skills, `AGENTS.md`, or `CLAUDE.md` from wiki notes.

Factory artifacts should stand on their own without requiring the external wiki.
