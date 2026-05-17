# AO Operator

[English](../../README.md) | [日本語](../ja/README.md) | [简体中文](../zh-Hans/README.md) | [繁體中文](../zh-Hant/README.md) | [한국어](../ko/README.md) | [Español](../es/README.md) | [Русский](../ru/README.md) | [Français](../fr/README.md) | **Deutsch** | [Português](../pt/README.md)

> AO ist die Abkürzung für **AI Orchestration Operation (Betrieb der
> KI-Orchestrierung)**. Produktname: **AO Operator**. Repository-Kennung auf GitHub:
> `ao-operator`.

> Dieses Dokument ist eine Übersetzung der englischen Fassung. Bei Abweichungen ist
> die englische Fassung maßgeblich:
> [`../../README.md`](../../README.md)

![CLI des autonomen Agenten AO Operator](../../images/ao-operator-agent-team.svg)

**AO Operator ist die Betriebsschicht für die KI-Orchestrierung. Sie beschreiben das
gewünschte Ergebnis in natürlicher Sprache, und das Werkzeug steuert Codex oder Claude
Code, bis verifizierte Ergebnisse vorliegen.** Erhält AO Operator eine
Produktanforderung, ein SDD oder eine Aufgabenbeschreibung, so übersetzt es diese in
abgegrenzte Rollen, plattformübergreifende Prüfungen, RunSpecs, Statusartefakte und
prüfbare Belege.

Wenn Sie wünschen, dass Ihre KI-CLI die Arbeit bis zum Abschluss bringt — und wenn Sie
die manuelle Pflege von Chatverläufen hinter sich lassen möchten — beginnen Sie hier.
AO Operator ist auf ergebnisorientiertes Arbeiten ausgelegt: Beispielanwendungen aus
Spezifikationen erzeugen, Repositories fortlaufend verbessern, das Verhalten auf
macOS, Ubuntu und Windows verifizieren sowie jede Rolle dazu verpflichten, vor der
Abnahme eines Laufs Belege vorzulegen.

AO Operator ist zugleich die Produktschicht über der umfassenderen AO-Adapter-Fläche.
OpenClaw übernimmt die Einreichung, Planung und Beobachtung der Arbeit; die
Warteschlangen der Hermes-Familie führen Läufe bis zur Worker-Sättigung aus; und AO
Runtime trägt darunter die Verteilung an Anbieter, die Richtlinien, die Ereignisse
und die Belege. AO Operator stellt für diese Plug-in- bzw. Adapter-Abläufe konsistente
Rollenverträge bereit, sodass nicht jede Integration die Semantik des Arbeitsflusses
neu erfinden muss.

## In Codex oder Claude Code einfügen (Paste Into Codex Or Claude Code)

Geben Sie nicht direkt Shell-Befehle ein. Beginnen Sie über die KI-CLI, die Sie
gewöhnlich verwenden. Öffnen Sie **Codex CLI** oder **Claude Code** in einem
übergeordneten Verzeichnis, in dem ein neuer Klon angelegt werden darf, und fügen Sie
die folgende Aufforderung ein:

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

(Der weitere Originaltext findet sich in [`../../README.md`](../../README.md).)

## Überblick (Overview)

AO Operator nimmt ein SDD (spezifikationsgesteuertes Dokument) oder eine
natürlichsprachige Aufgabenbeschreibung entgegen, koordiniert mehrere Agenten —
darunter Codex und Claude Code — auf Grundlage von **Rollenverträgen** und erzeugt
verifizierte Ergebnisse (Quellcode, Dokumentation, Belegpakete). Der Kern des
Produkts ruht auf drei Säulen:

1. **Rollenverträge**: Jeder Agent erklärt schriftlich, was er liefern muss, und die
   Prüfenden entscheiden auf Grundlage dieses Vertrags über die Abnahme.
2. **RunSpec**: Die Arbeit wird als ausführbarer DAG dargestellt und reproduzierbar
   auf AO Runtime ausgeführt.
3. **Belegpaket**: Ausführungsverlauf, Artefakte und Signaturen werden in einem
   einzigen auditierbaren Archiv zusammengefasst.

## Schnellstart (Quickstart)

Die detaillierte Anleitung finden Sie unter [`./quickstart.md`](./quickstart.md).
Die Einrichtung der Umgebung beschreibt [`./getting-started.md`](./getting-started.md).

## Lizenz (License)

AO Operator wird wahlweise unter einer der folgenden Lizenzen bereitgestellt:

- [Apache License, Version 2.0](../../LICENSE-APACHE)
- [MIT License](../../LICENSE-MIT)

Weitere Hinweise enthält die Datei [`NOTICE`](../../NOTICE).

Sofern nicht ausdrücklich anders angegeben, gelten alle wissentlich an dieses Projekt
übermittelten Beiträge als unter dem oben genannten dualen Lizenzmodell entsprechend
den Vorgaben der Apache-2.0-Lizenz eingebracht, ohne dass zusätzliche Bedingungen
Anwendung finden.

## Über diese Übersetzung (About This Translation)

Die deutsche Fassung wird schrittweise ergänzt. Glossar und Übersetzungsleitlinien
finden Sie in [`./TRANSLATION.md`](./TRANSLATION.md). Bei Abweichungen vom
englischen Original ist die englische Fassung maßgeblich.
