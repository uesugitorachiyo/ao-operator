# Guia de tradução e glossário (Translation Guide & Glossary)

Este diretório (`docs/pt/`) hospeda a versão em português do Brasil da documentação
do AO Operator. A fonte autoritativa continua sendo sempre a versão em inglês. A
tradução é adicionada de forma progressiva.

## Política de tradução (Translation Policy)

1. **O original é a fonte autoritativa (Source of Truth)**: quando a documentação em
   inglês muda, a versão em português é atualizada com algum atraso. Em caso de
   divergência, confie no texto em inglês.
2. **Não traduzir código nem identificadores (Do Not Translate Code/Identifiers)**:
   `RunSpec`, `SDD`, `factory_run`, as opções dos CLIs e os caminhos de arquivo
   permanecem inalterados.
3. **Registro formal (português do Brasil)**: utilize um registro escrito formal e
   trate a pessoa leitora com naturalidade, evitando coloquialismos.
4. **Prefira traduções consagradas em vez de estrangeirismos (Prefer Established
   Translations)**.

## Glossário (Glossary)

| English | Português | Observações (Notes) |
| --- | --- | --- |
| Operator | Operator | O nome do produto (AO Operator) é mantido sem tradução |
| Role contract | contrato de papel | |
| RunSpec | RunSpec | Não é traduzido |
| SDD | SDD (documento dirigido por especificação) | Esclarecido entre parênteses apenas na primeira ocorrência |
| Evidence pack | pacote de evidência | Tradução fixa |
| Closer | closer | Nome de papel |
| Profile | perfil | |
| Provider dispatch | despacho de provedores | |
| Smoke test | smoke test | |
| Status artifact | artefato de status | |
| Approval ticket | tíquete de aprovação | |

## Prioridades de tradução (Translation Priority)

1. Início do `README.md` (aproximadamente os três primeiros parágrafos)
2. `SETUP.md`
3. Seção "Paste Into Codex Or Claude Code" do `README.md`
4. Principais contratos de papel sob `docs/contracts/`
5. Demais conteúdos

## Antes de começar (Before You Start)

- Verifique a versão mais recente do original em inglês.
- Se algum termo importante estiver ausente do glossário, acrescente-o.
- Após concluir a tradução do trecho, remova o marcador
  `<!-- TRANSLATION PENDING -->`.
