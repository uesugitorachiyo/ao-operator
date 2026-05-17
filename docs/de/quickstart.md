# Schnellstart (Quickstart) — AO Operator

> Dieses Dokument ist eine Übersetzung der englischen Fassung. Bei Abweichungen ist
> die englische Fassung maßgeblich:
> Abschnitt „Paste Into Codex Or Claude Code“ in [`../../README.md`](../../README.md)

Diese Seite zeigt den kürzesten Weg, AO Operator aus Codex CLI oder Claude Code
auszuprobieren, das Beispiel-SDD zu materialisieren und die Belege einzusehen.

## In Codex oder Claude Code einfügen (Paste Into Codex or Claude Code)

Geben Sie keine Befehle direkt in die Shell ein. Öffnen Sie **Codex CLI** oder
**Claude Code** in einem übergeordneten Verzeichnis, in dem ein neuer Klon angelegt
werden darf, und fügen Sie den folgenden Prompt unverändert ein:

```text
Probieren Sie AO Operator aus, ohne aktive Anbieter-Token zu verwenden.

Ziele:
- Sofern das Repository noch nicht vorhanden ist, klonen Sie
  https://github.com/uesugitorachiyo/ao-operator.git.
- Wechseln Sie in dieses Repository.
- Lesen Sie examples/ingestible-specs/financial-citation-audit-sdd.md.
- Materialisieren Sie dieses SDD als Profil smoke-test über den
  Ingest-Pfad ohne Anbieter.
- Setzen Sie weder OPENAI_API_KEY noch ANTHROPIC_API_KEY.
- Falls Python 3 oder git nicht verfügbar sind, halten Sie an und erläutern Sie
  die Ursache.

Berichten Sie über:
- Die vom SDD geforderten Workflow-Ergebnisse
- Den öffentlichen Wedge, den AO Operator demonstriert
- Den von AO Operator erzeugten Rollengraphen
- Den Pfad des erzeugten RunSpec
- Den Pfad des Statusverzeichnisses
```

## Ein Beispiel-SDD materialisieren (Materialize a Sample SDD)

Falls Sie den Vorgang unmittelbar aus der Shell ausführen möchten, verwenden Sie die
folgenden Befehle. Python 3 und `git` sind erforderlich:

```bash
git clone https://github.com/uesugitorachiyo/ao-operator.git
cd ao-operator
python -m pip install -r requirements-dev.txt

python scripts/factory_run.py \
    --profile smoke-test \
    --spec examples/ingestible-specs/financial-citation-audit-sdd.md \
    --provider-free
```

Mit `--provider-free` wird ausschließlich der Ingest-Pfad ausgeführt, ohne dass
gegenüber den APIs von Codex oder Claude Kosten anfallen.

## Rollengraph und RunSpec einsehen

Nach Abschluss der Ausführung erzeugt AO Operator die folgenden Artefakte:

- `runs/<run-id>/role-graph.json` — Aus dem SDD abgeleiteter Rollenvertragsgraph
- `runs/<run-id>/runspec.yaml` — DAG-Spezifikation, die AO Runtime ausführt
- `runs/<run-id>/status/` — Von den einzelnen Rollen hinterlassene Statusartefakte
- `runs/<run-id>/evidence-pack-<run-id>.tar.zst` — Auditierbares Belegarchiv

## Abnahme durch den Closer prüfen (Closer Acceptance)

Die Rolle „Closer“ entscheidet, ob die von den einzelnen Rollen vorgelegten Belege
abnahmefähig sind. Die Entscheidung des Closers wird unter
`runs/<run-id>/status/closer/` gespeichert. Wird die Abnahme verweigert, werden die
fehlenden Belege konkret aufgeführt, was die Ursachenanalyse erleichtert.

## Nächste Schritte (Next Steps)

- [`./getting-started.md`](./getting-started.md) — Ausführliche Einrichtung
- [`./TRANSLATION.md`](./TRANSLATION.md) — Glossar
- [`../../SETUP.md`](../../SETUP.md) — Einrichtungsanleitung in englischer Sprache
- [`../../PROMPT_SAMPLES.md`](../../PROMPT_SAMPLES.md) — Häufig verwendete
  Prompt-Beispiele
- [`../../profiles/README.md`](../../profiles/README.md) — Profilschema
