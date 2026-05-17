# AO Operator

[English](../../README.md) | [日本語](../ja/README.md) | [简体中文](../zh-Hans/README.md) | [繁體中文](../zh-Hant/README.md) | [한국어](../ko/README.md) | **Español** | [Русский](../ru/README.md) | [Français](../fr/README.md) | [Deutsch](../de/README.md) | [Português](../pt/README.md)

> AO es la sigla de **AI Orchestration Operation (operación de orquestación de IA)**.
> Nombre del producto: **AO Operator**. Identificador del repositorio en GitHub: `ao-operator`.

> Este documento es una traducción de la versión en inglés. Si existieran discrepancias,
> la versión en inglés prevalece como fuente autoritativa:
> [`../../README.md`](../../README.md)

![CLI del agente autónomo AO Operator](../../images/ao-operator-agent-team.svg)

**AO Operator es la capa de operación para la orquestación de IA. Usted describe el
resultado deseado en lenguaje natural y la herramienta dirige a Codex o Claude Code
hasta producir entregables verificados.** Cuando se le proporciona una solicitud de
producto, un SDD o un resumen de tarea, AO Operator lo traduce a roles delimitados,
verificaciones multiplataforma, RunSpecs, artefactos de estado y evidencia revisable.

Si usted prefiere que su CLI de IA lleve el trabajo hasta su finalización — y desea
dejar atrás la gestión manual del historial de chat — comience por aquí. AO Operator
está diseñado para trabajo orientado a resultados: generar aplicaciones de ejemplo a
partir de especificaciones, mejorar repositorios de manera continua, verificar el
comportamiento en macOS / Ubuntu / Windows, y exigir que cada rol presente evidencia
antes de aceptar una ejecución.

AO Operator es además la capa de producto de la superficie más amplia de adaptadores
AO. OpenClaw se encarga del envío, la planificación y la observación del trabajo; las
colas de la familia Hermes gestionan ejecuciones con saturación de workers; y AO
Runtime asume por debajo el despacho de proveedores, las políticas, los eventos y la
evidencia. AO Operator ofrece contratos de rol coherentes para estos flujos basados en
adaptadores o complementos, de modo que cada integración no necesite reinventar la
semántica del flujo de trabajo.

## Pegar en Codex o Claude Code (Paste Into Codex Or Claude Code)

No escriba comandos de shell directamente. Comience desde el CLI de IA que ya utiliza.
Abra **Codex CLI** o **Claude Code** en un directorio padre donde sea posible crear un
nuevo clon y pegue el siguiente mensaje:

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

(Para el resto del texto original consulte [`../../README.md`](../../README.md).)

## Resumen (Overview)

AO Operator recibe un SDD (documento dirigido por especificación) o un resumen de
tarea en lenguaje natural, coordina varios agentes — incluidos Codex y Claude Code —
conforme a **contratos de rol** y produce entregables verificados (código,
documentación, paquetes de evidencia). El núcleo del producto se apoya en tres pilares:

1. **Contratos de rol**: cada agente declara por escrito qué debe entregar, y los
   evaluadores deciden la aceptación con base en ese contrato.
2. **RunSpec**: el trabajo se expresa como un DAG ejecutable que se ejecuta de forma
   reproducible sobre AO Runtime.
3. **Paquete de evidencia**: el historial de ejecución, los artefactos y las firmas
   se consolidan en un único archivo auditable.

## Inicio rápido (Quickstart)

Para los pasos detallados, consulte [`./quickstart.md`](./quickstart.md).
Para la configuración del entorno, consulte [`./getting-started.md`](./getting-started.md).

## Licencia (License)

AO Operator se ofrece bajo cualquiera de las siguientes licencias, a elección de la
persona usuaria:

- [Apache License, Version 2.0](../../LICENSE-APACHE)
- [MIT License](../../LICENSE-MIT)

Consulte además el archivo [`NOTICE`](../../NOTICE) para más detalles.

Salvo que se indique expresamente lo contrario, toda contribución enviada
intencionadamente a este proyecto se entiende ofrecida bajo el doble esquema de
licencias anterior, conforme a lo previsto por la licencia Apache-2.0, sin condiciones
adicionales.

## Sobre esta traducción (About This Translation)

Esta edición en español se está incorporando de forma progresiva. Para el glosario y
los criterios de traducción, consulte [`./TRANSLATION.md`](./TRANSLATION.md). Si se
detectan diferencias con el original en inglés, la versión en inglés prevalece como
fuente autoritativa.
