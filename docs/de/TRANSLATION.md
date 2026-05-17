# Übersetzungsleitfaden und Glossar (Translation Guide & Glossary)

Dieses Verzeichnis (`docs/de/`) enthält die deutsche Fassung der Dokumentation von
AO Operator. Die maßgebliche Fassung ist stets die englische. Die Übersetzung wird
schrittweise ergänzt.

## Übersetzungsleitlinien (Translation Policy)

1. **Maßgeblich ist das Original (Source of Truth)**: Wenn sich die englische
   Dokumentation ändert, zieht die deutsche Fassung mit gewisser Verzögerung nach.
   Bei Abweichungen ist die englische Fassung vorrangig.
2. **Code und Bezeichner werden nicht übersetzt (Do Not Translate
   Code/Identifiers)**: `RunSpec`, `SDD`, `factory_run`, CLI-Flags und Dateipfade
   bleiben unverändert.
3. **Formelle Anrede mit „Sie“**: Verwenden Sie ein formelles Schriftbild und
   sprechen Sie die lesende Person mit „Sie“ an.
4. **Bewährten deutschen Begriffen den Vorzug geben (Prefer Established
   Translations)**.

## Glossar (Glossary)

| English | Deutsch | Hinweise (Notes) |
| --- | --- | --- |
| Operator | Operator | Der Produktname (AO Operator) bleibt unverändert |
| Role contract | Rollenvertrag | |
| RunSpec | RunSpec | Nicht übersetzen |
| SDD | SDD (spezifikationsgesteuertes Dokument) | Erläuterung nur bei der ersten Nennung in Klammern |
| Evidence pack | Belegpaket | Feststehende Übersetzung |
| Closer | Closer | Rollenbezeichnung |
| Profile | Profil | |
| Provider dispatch | Anbieter-Dispatching | |
| Smoke test | Smoke-Test | |
| Status artifact | Statusartefakt | |
| Approval ticket | Freigabeticket | |

## Übersetzungspriorität (Translation Priority)

1. Anfang der `README.md` (etwa die ersten drei Absätze)
2. `SETUP.md`
3. Abschnitt „Paste Into Codex Or Claude Code“ in `README.md`
4. Wichtigste Rollenverträge unter `docs/contracts/`
5. Übrige Inhalte

## Vor Beginn der Arbeit (Before You Start)

- Prüfen Sie die aktuelle Fassung des englischen Originals.
- Ergänzen Sie wichtige Begriffe, die im Glossar fehlen.
- Entfernen Sie nach der Übersetzung den Marker `<!-- TRANSLATION PENDING -->`.
