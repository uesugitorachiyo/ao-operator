# Inicio rápido (Quickstart) — AO Operator

> Este documento es una traducción de la versión en inglés. Si existieran discrepancias,
> la versión en inglés prevalece como fuente autoritativa:
> sección "Paste Into Codex Or Claude Code" de [`../../README.md`](../../README.md)

Esta página describe la ruta más corta para probar AO Operator desde Codex CLI o
Claude Code, materializar el SDD de ejemplo y revisar la evidencia.

## Pegar en Codex o Claude Code (Paste Into Codex or Claude Code)

No escriba comandos directamente en la shell. Abra **Codex CLI** o **Claude Code** en
un directorio padre donde sea posible crear un nuevo clon y pegue el siguiente prompt
tal cual:

```text
Pruebe AO Operator sin utilizar tokens de proveedor reales.

Objetivos:
- Si aún no está disponible, clone https://github.com/uesugitorachiyo/ao-operator.git.
- Cámbiese a ese repositorio.
- Lea examples/ingestible-specs/financial-citation-audit-sdd.md.
- Materialice ese SDD como el perfil smoke-test utilizando la ruta de ingestión
  sin proveedor.
- No configure OPENAI_API_KEY ni ANTHROPIC_API_KEY.
- Si Python 3 o git no están disponibles, deténgase y explique la causa.

Informe de:
- Los resultados de flujo de trabajo que exige el SDD
- La cuña pública que AO Operator está demostrando
- El grafo de roles que AO Operator construyó
- La ruta del RunSpec generado
- La ruta del directorio de estado
```

## Materializar un SDD de ejemplo (Materialize a Sample SDD)

Si desea ejecutarlo directamente desde la shell, utilice los siguientes comandos. Se
requiere Python 3 y `git`:

```bash
git clone https://github.com/uesugitorachiyo/ao-operator.git
cd ao-operator
python -m pip install -r requirements-dev.txt

python scripts/factory_run.py \
    --profile smoke-test \
    --spec examples/ingestible-specs/financial-citation-audit-sdd.md \
    --provider-free
```

Al especificar `--provider-free` solo se ejercita la ruta de ingestión, sin generar
cargos contra las API de Codex o Claude.

## Revisar el grafo de roles y el RunSpec

Cuando la ejecución finaliza, AO Operator produce los siguientes artefactos:

- `runs/<run-id>/role-graph.json` — Grafo de contratos de rol derivado del SDD
- `runs/<run-id>/runspec.yaml` — Especificación del DAG que ejecuta AO Runtime
- `runs/<run-id>/status/` — Artefactos de estado que dejó cada rol
- `runs/<run-id>/evidence-pack-<run-id>.tar.zst` — Archivo de evidencia auditable

## Comprobar la aceptación del closer (Closer Acceptance)

El rol "closer" decide si la evidencia presentada por cada rol resulta aceptable. La
decisión del closer se almacena en `runs/<run-id>/status/closer/`. Cuando rechaza la
ejecución, enumera de forma específica qué evidencias faltan, lo que facilita rastrear
la causa raíz.

## Siguientes pasos (Next Steps)

- [`./getting-started.md`](./getting-started.md) — Configuración detallada
- [`./TRANSLATION.md`](./TRANSLATION.md) — Glosario
- [`../../SETUP.md`](../../SETUP.md) — Instrucciones de configuración en inglés
- [`../../PROMPT_SAMPLES.md`](../../PROMPT_SAMPLES.md) — Ejemplos de prompts de uso
  habitual
- [`../../profiles/README.md`](../../profiles/README.md) — Esquema de perfiles
