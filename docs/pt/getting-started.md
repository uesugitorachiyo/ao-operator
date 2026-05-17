# Primeiros passos (Getting Started) — AO Operator

> Este documento é uma tradução da versão em inglês. Em caso de divergências, a
> versão em inglês prevalece como fonte autoritativa:
> [`../../SETUP.md`](../../SETUP.md)

Esta página descreve os passos mínimos para instalar o AO Operator em uma máquina de
desenvolvimento local e materializar o primeiro SDD de exemplo.

## Pré-requisitos (Prerequisites)

- **Sistema operacional**: macOS, Ubuntu ou Windows (recomenda-se o WSL2)
- **Python**: versão 3.10 ou superior
- **git**
- **Provedor (opcional)**: Codex CLI ou Claude Code (dispensável caso você queira
  apenas experimentar o modo provider-free)
- **Opcional**: instalação local do AO Runtime (necessária para executar com
  `--engine ao`)

## Instalação (Install)

```bash
git clone https://github.com/uesugitorachiyo/ao-operator.git
cd ao-operator

# Crie um ambiente virtual (recomendado)
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate

# Instale as dependências de desenvolvimento
python -m pip install -r requirements-dev.txt
```

Para a configuração detalhada dos provedores (chaves de API, caminhos para os
binários dos CLIs etc.), consulte [`../../SETUP.md`](../../SETUP.md).

## Verificação (Verify)

Execute os smoke tests:

```bash
python -m pytest -q
```

Esse comando verifica de forma abrangente a consistência dos contratos de papel do AO
Operator, a geração de RunSpecs e os artefatos de status (é o mesmo conjunto de
testes executado no CI).

## Materializar um SDD de exemplo (Materialize a Sample SDD)

Materialize o SDD de exemplo no modo sem provedor:

```bash
python scripts/factory_run.py \
    --profile smoke-test \
    --spec examples/ingestible-specs/financial-citation-audit-sdd.md \
    --provider-free
```

Os artefatos são gravados em `runs/<run-id>/`. Para mais detalhes, consulte
[`./quickstart.md`](./quickstart.md).

## Próximos passos (Next Steps)

- [`./quickstart.md`](./quickstart.md) — Passos para experimentar o AO Operator a
  partir do Codex ou do Claude Code
- [`./TRANSLATION.md`](./TRANSLATION.md) — Glossário e critérios de tradução
- [`../../SETUP.md`](../../SETUP.md) — Configuração detalhada (em inglês)
- [`../../PROMPT_SAMPLES.md`](../../PROMPT_SAMPLES.md) — Exemplos de prompts de uso
  frequente (em inglês)
- [`../../profiles/README.md`](../../profiles/README.md) — Esquema de perfis (em
  inglês)
