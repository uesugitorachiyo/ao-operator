# Guide de traduction et glossaire (Translation Guide & Glossary)

Ce répertoire (`docs/fr/`) accueille la version française de la documentation
d'AO Operator. La source faisant foi reste toujours la version anglaise. La traduction
est ajoutée de manière progressive.

## Politique de traduction (Translation Policy)

1. **L'original fait foi (Source of Truth)** : lorsque la documentation anglaise
   évolue, la version française est mise à jour avec un certain décalage. En cas de
   divergence, faites confiance à l'anglais.
2. **Ne pas traduire le code ni les identifiants (Do Not Translate
   Code/Identifiers)** : `RunSpec`, `SDD`, `factory_run`, les options des CLI et les
   chemins de fichier restent inchangés.
3. **Registre formel (vouvoiement)** : utilisez un registre écrit formel et
   vouvoyez la personne qui lit.
4. **Préférez les traductions établies aux anglicismes (Prefer Established
   Translations)**.

## Glossaire (Glossary)

| English | Français | Notes |
| --- | --- | --- |
| Operator | Operator | Le nom du produit (AO Operator) reste tel quel |
| Role contract | contrat de rôle | |
| RunSpec | RunSpec | Non traduit |
| SDD | SDD (document piloté par la spécification) | Précisez entre parenthèses uniquement à la première occurrence |
| Evidence pack | paquet de preuves | Traduction figée |
| Closer | closer | Nom de rôle |
| Profile | profil | |
| Provider dispatch | distribution vers les fournisseurs | |
| Smoke test | test de fumée | |
| Status artifact | artefact de statut | |
| Approval ticket | ticket d'approbation | |

## Priorités de traduction (Translation Priority)

1. Début de `README.md` (environ les trois premiers paragraphes)
2. `SETUP.md`
3. Section « Paste Into Codex Or Claude Code » de `README.md`
4. Principaux contrats de rôle sous `docs/contracts/`
5. Reste de la documentation

## Avant de commencer (Before You Start)

- Vérifiez la dernière version de l'original en anglais.
- Si un terme important manque au glossaire, ajoutez-le.
- Une fois la traduction réalisée, retirez le marqueur
  `<!-- TRANSLATION PENDING -->`.
