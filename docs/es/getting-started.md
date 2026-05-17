# Primeros pasos (Getting Started) — AO Operator

> Este documento es una traducción de la versión en inglés. Si existieran discrepancias,
> la versión en inglés prevalece como fuente autoritativa:
> [`../../SETUP.md`](../../SETUP.md)

Esta página describe los pasos mínimos para instalar AO Operator en una máquina de
desarrollo local y materializar el primer SDD de ejemplo.

## Requisitos previos (Prerequisites)

- **Sistema operativo**: macOS, Ubuntu o Windows (se recomienda WSL2)
- **Python**: 3.10 o superior
- **git**
- **Proveedor (opcional)**: Codex CLI o Claude Code (no es necesario si va a probar el
  modo provider-free)
- **Opcional**: instalación local de AO Runtime (necesaria si se ejecuta con
  `--engine ao`)

## Instalación (Install)

```bash
git clone https://github.com/uesugitorachiyo/ao-operator.git
cd ao-operator

# Cree un entorno virtual (recomendado)
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate

# Instale las dependencias de desarrollo
python -m pip install -r requirements-dev.txt
```

Para la configuración detallada de los proveedores (claves de API, rutas a binarios de
CLI, etc.) consulte [`../../SETUP.md`](../../SETUP.md).

## Verificación (Verify)

Ejecute las pruebas de humo:

```bash
python -m pytest -q
```

Este comando comprueba de forma integral la consistencia de los contratos de rol, la
generación de RunSpec y los artefactos de estado de AO Operator (es el mismo conjunto
de pruebas que se ejecuta en CI).

## Materializar un SDD de ejemplo (Materialize a Sample SDD)

Materialice el SDD de ejemplo en modo sin proveedor:

```bash
python scripts/factory_run.py \
    --profile smoke-test \
    --spec examples/ingestible-specs/financial-citation-audit-sdd.md \
    --provider-free
```

Los artefactos se guardan bajo `runs/<run-id>/`. Para más detalles consulte
[`./quickstart.md`](./quickstart.md).

## Siguientes pasos (Next Steps)

- [`./quickstart.md`](./quickstart.md) — Pasos para probar AO Operator desde Codex o
  Claude Code
- [`./TRANSLATION.md`](./TRANSLATION.md) — Glosario y criterios de traducción
- [`../../SETUP.md`](../../SETUP.md) — Configuración detallada (en inglés)
- [`../../PROMPT_SAMPLES.md`](../../PROMPT_SAMPLES.md) — Ejemplos de prompts de uso
  habitual (en inglés)
- [`../../profiles/README.md`](../../profiles/README.md) — Esquema de perfiles
  (en inglés)
