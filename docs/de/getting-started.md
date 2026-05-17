# Erste Schritte (Getting Started) — AO Operator

> Dieses Dokument ist eine Übersetzung der englischen Fassung. Bei Abweichungen ist
> die englische Fassung maßgeblich:
> [`../../SETUP.md`](../../SETUP.md)

Diese Seite beschreibt die Mindestschritte, um AO Operator auf einer lokalen
Entwicklungsmaschine einzurichten und ein erstes Beispiel-SDD zu materialisieren.

## Voraussetzungen (Prerequisites)

- **Betriebssystem**: macOS, Ubuntu oder Windows (WSL2 wird empfohlen)
- **Python**: 3.10 oder neuer
- **git**
- **Anbieter (optional)**: Codex CLI oder Claude Code (nicht erforderlich, wenn Sie
  ausschließlich den Modus provider-free ausprobieren möchten)
- **Optional**: lokale Installation von AO Runtime (erforderlich für die Ausführung
  mit `--engine ao`)

## Installation (Install)

```bash
git clone https://github.com/uesugitorachiyo/ao-operator.git
cd ao-operator

# Legen Sie eine virtuelle Umgebung an (empfohlen)
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate

# Installieren Sie die Entwicklungsabhängigkeiten
python -m pip install -r requirements-dev.txt
```

Einzelheiten zur Anbieterkonfiguration (API-Schlüssel, Pfade zu CLI-Binärdateien
usw.) entnehmen Sie bitte [`../../SETUP.md`](../../SETUP.md).

## Funktionsprüfung (Verify)

Führen Sie die Smoke-Tests aus:

```bash
python -m pytest -q
```

Dieser Befehl prüft umfassend die Konsistenz der Rollenverträge von AO Operator, die
Erzeugung von RunSpecs sowie die Statusartefakte (es handelt sich um dieselbe
Testreihe, die auch in der CI ausgeführt wird).

## Ein Beispiel-SDD materialisieren (Materialize a Sample SDD)

Materialisieren Sie das Beispiel-SDD im Modus ohne Anbieter:

```bash
python scripts/factory_run.py \
    --profile smoke-test \
    --spec examples/ingestible-specs/financial-citation-audit-sdd.md \
    --provider-free
```

Die Artefakte werden unter `runs/<run-id>/` abgelegt. Weitere Einzelheiten finden Sie
in [`./quickstart.md`](./quickstart.md).

## Nächste Schritte (Next Steps)

- [`./quickstart.md`](./quickstart.md) — Anleitung zum Ausprobieren von AO Operator
  aus Codex oder Claude Code heraus
- [`./TRANSLATION.md`](./TRANSLATION.md) — Glossar und Übersetzungsleitlinien
- [`../../SETUP.md`](../../SETUP.md) — Ausführliche Einrichtungsanleitung (englisch)
- [`../../PROMPT_SAMPLES.md`](../../PROMPT_SAMPLES.md) — Häufig verwendete
  Prompt-Beispiele (englisch)
- [`../../profiles/README.md`](../../profiles/README.md) — Profilschema (englisch)
