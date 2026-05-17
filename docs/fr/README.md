# AO Operator

[English](../../README.md) | [日本語](../ja/README.md) | [简体中文](../zh-Hans/README.md) | [繁體中文](../zh-Hant/README.md) | [한국어](../ko/README.md) | [Español](../es/README.md) | [Русский](../ru/README.md) | **Français** | [Deutsch](../de/README.md) | [Português](../pt/README.md)

> AO est l'abréviation de **AI Orchestration Operation (exploitation
> d'orchestration d'IA)**. Nom du produit : **AO Operator**. Identifiant du dépôt
> GitHub : `ao-operator`.

> Le présent document est une traduction de la version anglaise. En cas de divergence,
> la version anglaise fait foi :
> [`../../README.md`](../../README.md)

![CLI de l'agent autonome AO Operator](../../images/ao-operator-agent-team.svg)

**AO Operator est la couche d'exploitation de l'orchestration d'IA. Vous décrivez le
résultat attendu en langage naturel, et l'outil pilote Codex ou Claude Code jusqu'à
obtenir des livrables vérifiés.** Lorsqu'on lui transmet une demande produit, un SDD
ou une note de tâche, AO Operator les traduit en rôles délimités, en vérifications
multiplateformes, en RunSpec, en artefacts de statut et en preuves vérifiables.

Si vous souhaitez que votre CLI d'IA mène le travail jusqu'à son terme — et si vous
voulez tourner la page de la gestion manuelle des historiques de conversation —
commencez ici. AO Operator est conçu pour un travail orienté résultats : générer des
applications d'exemple à partir de spécifications, améliorer un dépôt de façon
continue, vérifier les comportements sur macOS, Ubuntu et Windows, ou encore obliger
chaque rôle à présenter des preuves avant qu'une exécution puisse être acceptée.

AO Operator constitue par ailleurs la couche produit qui repose sur la surface plus
large des adaptateurs AO. OpenClaw prend en charge la soumission, l'ordonnancement et
l'observation du travail ; les files d'attente de la famille Hermes gèrent les
exécutions à saturation des workers ; et AO Runtime assume, en dessous, la
distribution vers les fournisseurs, les politiques, les événements et les preuves. AO
Operator offre à ces flux à base d'adaptateurs ou de greffons des contrats de rôle
cohérents, ce qui évite à chaque intégration de réinventer la sémantique de ses
processus.

## Coller dans Codex ou Claude Code (Paste Into Codex Or Claude Code)

N'entrez pas directement des commandes shell. Commencez à partir du CLI d'IA que vous
utilisez habituellement. Ouvrez **Codex CLI** ou **Claude Code** dans un répertoire
parent dans lequel il est possible de créer un nouveau clone, puis collez le message
suivant :

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

(Pour la suite du texte original, consultez [`../../README.md`](../../README.md).)

## Aperçu (Overview)

AO Operator reçoit un SDD (document piloté par la spécification) ou une note de tâche
en langage naturel, coordonne plusieurs agents — dont Codex et Claude Code — sur la
base de **contrats de rôle**, puis produit des livrables vérifiés (code,
documentation, paquets de preuves). Le noyau du produit repose sur trois piliers :

1. **Contrats de rôle** : chaque agent déclare par écrit ce qu'il doit livrer, et les
   évaluateurs décident de l'acceptation sur la base de ce contrat.
2. **RunSpec** : le travail est représenté comme un DAG exécutable, exécuté de
   manière reproductible sur AO Runtime.
3. **Paquet de preuves** : l'historique d'exécution, les artefacts et les signatures
   sont consolidés en une seule archive auditable.

## Démarrage rapide (Quickstart)

Pour la procédure détaillée, consultez [`./quickstart.md`](./quickstart.md).
Pour la configuration de l'environnement, consultez
[`./getting-started.md`](./getting-started.md).

## Licence (License)

AO Operator est distribué, au choix de l'utilisateur, selon l'une des licences
suivantes :

- [Apache License, Version 2.0](../../LICENSE-APACHE)
- [MIT License](../../LICENSE-MIT)

Consultez également le fichier [`NOTICE`](../../NOTICE) pour plus de détails.

Sauf indication expresse contraire, toute contribution soumise intentionnellement à
ce projet est réputée fournie sous le régime de double licence ci-dessus, dans les
conditions définies par la licence Apache-2.0, sans clause supplémentaire.

## À propos de cette traduction (About This Translation)

La présente version française est intégrée de façon progressive. Pour le glossaire et
les principes de traduction, consultez [`./TRANSLATION.md`](./TRANSLATION.md). En cas
de divergence avec l'original anglais, la version anglaise fait foi.
