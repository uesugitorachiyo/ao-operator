# Démarrage rapide (Quickstart) — AO Operator

> Le présent document est une traduction de la version anglaise. En cas de divergence,
> la version anglaise fait foi :
> section « Paste Into Codex Or Claude Code » de [`../../README.md`](../../README.md)

Cette page décrit le chemin le plus court pour essayer AO Operator depuis Codex CLI
ou Claude Code, matérialiser le SDD d'exemple et consulter les preuves.

## Coller dans Codex ou Claude Code (Paste Into Codex or Claude Code)

N'entrez pas directement de commandes dans le shell. Ouvrez **Codex CLI** ou
**Claude Code** dans un répertoire parent dans lequel il est possible de créer un
nouveau clone, et collez le prompt suivant tel quel :

```text
Essayez AO Operator sans utiliser de jetons de fournisseur réels.

Objectifs :
- Si le dépôt n'a pas encore été récupéré, clonez
  https://github.com/uesugitorachiyo/ao-operator.git.
- Placez-vous dans ce dépôt.
- Lisez examples/ingestible-specs/financial-citation-audit-sdd.md.
- Matérialisez ce SDD en tant que profil smoke-test en utilisant le chemin
  d'ingestion sans fournisseur.
- Ne définissez pas OPENAI_API_KEY ni ANTHROPIC_API_KEY.
- Si Python 3 ou git ne sont pas disponibles, arrêtez-vous et expliquez la cause.

Indiquez :
- Les résultats de flux de travail exigés par le SDD
- Le coin public dont AO Operator fait la démonstration
- Le graphe de rôles construit par AO Operator
- Le chemin du RunSpec généré
- Le chemin du répertoire de statut
```

## Matérialiser un SDD d'exemple (Materialize a Sample SDD)

Si vous souhaitez l'exécuter directement depuis le shell, utilisez les commandes
suivantes. Python 3 et `git` sont requis :

```bash
git clone https://github.com/uesugitorachiyo/ao-operator.git
cd ao-operator
python -m pip install -r requirements-dev.txt

python scripts/factory_run.py \
    --profile smoke-test \
    --spec examples/ingestible-specs/financial-citation-audit-sdd.md \
    --provider-free
```

En spécifiant `--provider-free`, seul le chemin d'ingestion est exercé, sans
générer de frais sur les API de Codex ou de Claude.

## Consulter le graphe de rôles et le RunSpec

À l'issue de l'exécution, AO Operator produit les artefacts suivants :

- `runs/<run-id>/role-graph.json` — Graphe des contrats de rôle dérivé du SDD
- `runs/<run-id>/runspec.yaml` — Spécification du DAG exécutée par AO Runtime
- `runs/<run-id>/status/` — Artefacts de statut laissés par chaque rôle
- `runs/<run-id>/evidence-pack-<run-id>.tar.zst` — Archive de preuves auditable

## Vérifier l'acceptation par le closer (Closer Acceptance)

Le rôle « closer » décide si les preuves présentées par chaque rôle sont acceptables.
La décision du closer est consignée sous `runs/<run-id>/status/closer/`. En cas de
refus, les preuves manquantes sont énumérées de façon spécifique, ce qui facilite
l'identification de la cause racine.

## Étapes suivantes (Next Steps)

- [`./getting-started.md`](./getting-started.md) — Configuration détaillée
- [`./TRANSLATION.md`](./TRANSLATION.md) — Glossaire
- [`../../SETUP.md`](../../SETUP.md) — Procédure d'installation en anglais
- [`../../PROMPT_SAMPLES.md`](../../PROMPT_SAMPLES.md) — Exemples de prompts
  fréquemment utilisés
- [`../../profiles/README.md`](../../profiles/README.md) — Schéma des profils
