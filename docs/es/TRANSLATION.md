# Guía de traducción y glosario (Translation Guide & Glossary)

Este directorio (`docs/es/`) aloja la versión en español de la documentación de AO
Operator. La fuente autoritativa es siempre la versión en inglés. La traducción se
incorpora de forma progresiva.

## Política de traducción (Translation Policy)

1. **El original es la fuente autoritativa (Source of Truth)**: si la documentación en
   inglés cambia, la versión en español se actualiza con cierto desfase. Ante cualquier
   discrepancia, prevalece el inglés.
2. **No traducir código ni identificadores (Do Not Translate Code/Identifiers)**:
   `RunSpec`, `SDD`, `factory_run`, los flags de CLI y las rutas de archivo permanecen
   sin traducir.
3. **Registro formal (usted)**: utilice un registro escrito formal, dirigiéndose a la
   persona lectora con "usted".
4. **Prefiera traducciones consolidadas frente a anglicismos (Prefer Established
   Translations)**.

## Glosario (Glossary)

| English | Español | Notas (Notes) |
| --- | --- | --- |
| Operator | Operator | El nombre del producto (AO Operator) se conserva sin traducir |
| Role contract | contrato de rol | |
| RunSpec | RunSpec | No se traduce |
| SDD | SDD (documento dirigido por especificación) | Se aclara entre paréntesis solo en la primera aparición |
| Evidence pack | paquete de evidencia | Traducción fija |
| Closer | closer | Nombre de rol |
| Profile | perfil | |
| Provider dispatch | despacho de proveedores | |
| Smoke test | prueba de humo | |
| Status artifact | artefacto de estado | |
| Approval ticket | ticket de aprobación | |

## Prioridades de traducción (Translation Priority)

1. Encabezamiento de `README.md` (aproximadamente los tres primeros párrafos)
2. `SETUP.md`
3. Sección "Paste Into Codex Or Claude Code" de `README.md`
4. Contratos de rol principales bajo `docs/contracts/`
5. Resto del material

## Antes de empezar (Before You Start)

- Verifique la última versión del original en inglés.
- Si encuentra términos importantes ausentes del glosario, agréguelos.
- Una vez traducido el fragmento, elimine el marcador
  `<!-- TRANSLATION PENDING -->`.
