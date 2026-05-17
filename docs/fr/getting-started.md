# Pour commencer (Getting Started) — AO Operator

> Le présent document est une traduction de la version anglaise. En cas de divergence,
> la version anglaise fait foi :
> [`../../SETUP.md`](../../SETUP.md)

Cette page présente la procédure minimale pour installer AO Operator sur un poste de
développement local et matérialiser un premier SDD d'exemple.

## Prérequis (Prerequisites)

- **Système d'exploitation** : macOS, Ubuntu ou Windows (WSL2 recommandé)
- **Python** : version 3.10 ou supérieure
- **git**
- **Fournisseur (facultatif)** : Codex CLI ou Claude Code (inutile si vous souhaitez
  uniquement essayer le mode provider-free)
- **Facultatif** : installation locale d'AO Runtime (nécessaire pour l'exécution avec
  `--engine ao`)

## Installation (Install)

```bash
git clone https://github.com/uesugitorachiyo/ao-operator.git
cd ao-operator

# Créez un environnement virtuel (recommandé)
python -m venv .venv
source .venv/bin/activate    # Windows : .venv\Scripts\activate

# Installez les dépendances de développement
python -m pip install -r requirements-dev.txt
```

Pour la configuration détaillée des fournisseurs (clés d'API, chemins vers les
binaires des CLI, etc.), consultez [`../../SETUP.md`](../../SETUP.md).

## Vérification (Verify)

Exécutez les tests de fumée :

```bash
python -m pytest -q
```

Cette commande contrôle de manière exhaustive la cohérence des contrats de rôle
d'AO Operator, la génération des RunSpec et les artefacts de statut (il s'agit du
même ensemble de tests que celui exécuté en CI).

## Matérialiser un SDD d'exemple (Materialize a Sample SDD)

Matérialisez le SDD d'exemple en mode sans fournisseur :

```bash
python scripts/factory_run.py \
    --profile smoke-test \
    --spec examples/ingestible-specs/financial-citation-audit-sdd.md \
    --provider-free
```

Les artefacts sont enregistrés sous `runs/<run-id>/`. Pour plus de détails, consultez
[`./quickstart.md`](./quickstart.md).

## Étapes suivantes (Next Steps)

- [`./quickstart.md`](./quickstart.md) — Procédure pour essayer AO Operator depuis
  Codex ou Claude Code
- [`./TRANSLATION.md`](./TRANSLATION.md) — Glossaire et principes de traduction
- [`../../SETUP.md`](../../SETUP.md) — Configuration détaillée (en anglais)
- [`../../PROMPT_SAMPLES.md`](../../PROMPT_SAMPLES.md) — Exemples de prompts
  fréquemment utilisés (en anglais)
- [`../../profiles/README.md`](../../profiles/README.md) — Schéma des profils
  (en anglais)
