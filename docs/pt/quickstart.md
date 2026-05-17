# Início rápido (Quickstart) — AO Operator

> Este documento é uma tradução da versão em inglês. Em caso de divergências, a
> versão em inglês prevalece como fonte autoritativa:
> seção "Paste Into Codex Or Claude Code" de [`../../README.md`](../../README.md)

Esta página descreve o caminho mais curto para experimentar o AO Operator a partir
do Codex CLI ou do Claude Code, materializar o SDD de exemplo e revisar as
evidências.

## Colar no Codex ou no Claude Code (Paste Into Codex or Claude Code)

Não digite comandos diretamente no shell. Abra o **Codex CLI** ou o **Claude Code**
em um diretório pai onde seja possível criar um novo clone e cole o prompt a seguir
sem alterações:

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

## Materializar um SDD de exemplo (Materialize a Sample SDD)

Se você quiser executar diretamente a partir do shell, use os comandos a seguir. São
necessários Python 3 e `git`:

```bash
git clone https://github.com/uesugitorachiyo/ao-operator.git
cd ao-operator
python -m pip install -r requirements-dev.txt

python scripts/factory_run.py \
    --profile smoke-test \
    --spec examples/ingestible-specs/financial-citation-audit-sdd.md \
    --provider-free
```

Ao especificar `--provider-free`, apenas o caminho de ingestão é exercitado, sem
gerar cobranças contra as APIs do Codex ou do Claude.

## Inspecionar o grafo de papéis e o RunSpec

Quando a execução é concluída, o AO Operator produz os seguintes artefatos:

- `runs/<run-id>/role-graph.json` — Grafo de contratos de papel derivado do SDD
- `runs/<run-id>/runspec.yaml` — Especificação de DAG executada pelo AO Runtime
- `runs/<run-id>/status/` — Artefatos de status deixados por cada papel
- `runs/<run-id>/evidence-pack-<run-id>.tar.zst` — Arquivo auditável de evidências

## Verificar a aceitação do closer (Closer Acceptance)

O papel "closer" decide se as evidências apresentadas por cada papel podem ser
aceitas. A decisão do closer é gravada em `runs/<run-id>/status/closer/`. Quando a
execução é recusada, são listadas, de forma específica, quais evidências estão
faltando, o que facilita rastrear a causa raiz.

## Próximos passos (Next Steps)

- [`./getting-started.md`](./getting-started.md) — Configuração detalhada
- [`./TRANSLATION.md`](./TRANSLATION.md) — Glossário
- [`../../SETUP.md`](../../SETUP.md) — Instruções de configuração em inglês
- [`../../PROMPT_SAMPLES.md`](../../PROMPT_SAMPLES.md) — Exemplos de prompts de uso
  frequente
- [`../../profiles/README.md`](../../profiles/README.md) — Esquema de perfis
