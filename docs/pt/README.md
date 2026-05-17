# AO Operator

[English](../../README.md) | [日本語](../ja/README.md) | [简体中文](../zh-Hans/README.md) | [繁體中文](../zh-Hant/README.md) | [한국어](../ko/README.md) | [Español](../es/README.md) | [Русский](../ru/README.md) | [Français](../fr/README.md) | [Deutsch](../de/README.md) | **Português**

> AO é a sigla de **AI Orchestration Operation (operação de orquestração de IA)**.
> Nome do produto: **AO Operator**. Identificador do repositório no GitHub:
> `ao-operator`.

> Este documento é uma tradução da versão em inglês. Em caso de divergências, a
> versão em inglês prevalece como fonte autoritativa:
> [`../../README.md`](../../README.md)

![CLI do agente autônomo AO Operator](../../images/ao-operator-agent-team.svg)

**O AO Operator é a camada de operação para a orquestração de IA. Você descreve o
resultado desejado em linguagem natural e a ferramenta conduz o Codex ou o Claude
Code até produzir entregas verificadas.** Ao receber uma solicitação de produto, um
SDD ou um resumo de tarefa, o AO Operator traduz tudo isso em papéis com escopo
definido, verificações multiplataforma, RunSpecs, artefatos de status e evidências
revisáveis.

Se você prefere que o seu CLI de IA leve o trabalho até a conclusão — e quer deixar
para trás o gerenciamento manual do histórico de conversa — comece por aqui. O AO
Operator foi pensado para um trabalho orientado a resultados: gerar aplicativos de
exemplo a partir de especificações, melhorar repositórios de forma contínua,
verificar o comportamento em macOS, Ubuntu e Windows, e exigir que cada papel
apresente evidências antes de uma execução ser aceita.

O AO Operator também é a camada de produto sobre a superfície mais ampla de
adaptadores AO. O OpenClaw cuida da submissão, do agendamento e da observação do
trabalho; as filas da família Hermes lidam com execuções que saturam os workers; e o
AO Runtime assume, na camada inferior, o despacho para provedores, as políticas, os
eventos e as evidências. O AO Operator oferece contratos de papel consistentes para
esses fluxos baseados em plug-ins e adaptadores, de modo que cada integração não
precise reinventar a semântica do fluxo de trabalho.

## Colar no Codex ou no Claude Code (Paste Into Codex Or Claude Code)

Não digite comandos de shell diretamente. Comece a partir do CLI de IA que você
costuma usar. Abra o **Codex CLI** ou o **Claude Code** em um diretório pai onde seja
possível criar um novo clone e cole a seguinte mensagem:

```text
Experimente o AO Operator sem usar tokens de provedor reais.

Objetivos:
- Se ainda não houver o repositório, clone
  https://github.com/uesugitorachiyo/ao-operator.git.
- Entre nesse repositório.
- Leia examples/ingestible-specs/financial-citation-audit-sdd.md.
- Materialize esse SDD como o perfil smoke-test usando o caminho de ingestão
  sem provedor.
- Não defina OPENAI_API_KEY nem ANTHROPIC_API_KEY.
- Se Python 3 ou git não estiverem disponíveis, interrompa o processo e explique
  a causa.

Relate:
- Os resultados de fluxo de trabalho exigidos pelo SDD
- O wedge público que o AO Operator está demonstrando
- O grafo de papéis que o AO Operator construiu
- O caminho do RunSpec gerado
- O caminho do diretório de status
```

(Para o restante do texto original, consulte [`../../README.md`](../../README.md).)

## Visão geral (Overview)

O AO Operator recebe um SDD (documento dirigido por especificação) ou um resumo de
tarefa em linguagem natural, coordena vários agentes — incluindo Codex e Claude Code
— com base em **contratos de papel** e produz entregas verificadas (código,
documentação, pacotes de evidência). O núcleo do produto se apoia em três pilares:

1. **Contratos de papel**: cada agente declara por escrito o que deve entregar e os
   avaliadores decidem sobre a aceitação com base nesse contrato.
2. **RunSpec**: o trabalho é representado como um DAG executável, executado de forma
   reprodutível sobre o AO Runtime.
3. **Pacote de evidência**: histórico de execução, artefatos e assinaturas são
   consolidados em um único arquivo auditável.

## Início rápido (Quickstart)

Para o passo a passo detalhado, consulte [`./quickstart.md`](./quickstart.md).
Para a configuração do ambiente, consulte
[`./getting-started.md`](./getting-started.md).

## Licença (License)

O AO Operator é distribuído sob uma das licenças a seguir, a critério da pessoa
usuária:

- [Apache License, Version 2.0](../../LICENSE-APACHE)
- [MIT License](../../LICENSE-MIT)

Consulte também o arquivo [`NOTICE`](../../NOTICE) para mais detalhes.

Salvo indicação expressa em contrário, qualquer contribuição enviada
intencionalmente a este projeto é considerada fornecida sob o esquema duplo de
licenciamento acima, nos termos previstos pela licença Apache-2.0, sem condições
adicionais.

## Sobre esta tradução (About This Translation)

A versão em português do Brasil é adicionada de forma progressiva. Para o glossário
e os critérios de tradução, consulte [`./TRANSLATION.md`](./TRANSLATION.md). Em caso
de divergências em relação ao original em inglês, a versão em inglês prevalece como
fonte autoritativa.
