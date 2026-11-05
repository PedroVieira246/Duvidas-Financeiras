# 13 · Ajustes da v0.3.0 – executável configurável por planilha (calibração)

**Data:** 05/11/2026 · **Base:** v0.2.1 (`rpa_duvidas_financeiras_v0.2.0\`, sem alteração) · **Fonte:** `Especificacao_Tecnica_v0.3.0_EXE_Calibracao.md` (v1.0)

## 1. Decisões da análise (Etapa 1)

| # | Ponto | Decisão |
| --- | --- | --- |
| 1 | Seção 6.2, item 4: a trava "só o destino padrão" também valia para `enviar_novo()`, que envia os avisos para AVISO_ERRO | Trava **por operação**. `responder` e `encaminhar` só saem para o destino padrão. `enviar_novo` sai para o destino padrão ou AVISO_ERRO. Com `ENCAMINHAR`, o encaminhamento vai ao destino padrão. |
| 2 | Com `marcar_nao_fornecedores = N`, os e-mails que não são de fornecedores voltariam a cada ciclo e ocupariam o lote | O filtro de remetente roda **dentro da varredura da caixa, antes do lote**. Os e-mails recusados não são convertidos nem alterados; só contam em `nao_fornecedores`. |
| 3 | Status do caso manual com `CATEGORIZAR` | Ação `ENCAMINHAR_MANUAL`, status `CONCLUIDO`, `enviado = N`, categoria `RPA - Encaminhado` e .msg arquivado. O `reprocessar` não libera esses e-mails. |
| 4 | Ação `RESPONDER_TEXTO` da aba Categorias, sem comportamento definido | Responde só com o texto da aba Textos, sem anexo; o "Código do texto" é obrigatório. Ações aceitas: `TUT_*` → tutorial, texto ou manual; `FORMS_PO` → forms, texto ou manual; `MANUAL*` → só manual. |
| 5 | Aba Palavras_chave: a regra geral é "linha 1 = cabeçalho", mas os parâmetros ficam no topo | `peso_assunto` e `saturacao` nas linhas 1 e 2 (área protegida), cabeçalho na linha 4. O leitor localiza o cabeçalho pelo nome. |
| 6 | "Marcado como lido" na caixa pessoal | Segue a especificação: o e-mail tratado é marcado como lido. O e-mail já tratado pelo analista só recebe a categoria. |

## 2. Alterações no código

| Arquivo | O que mudou |
| --- | --- |
| `config_xlsx_esquema.py` (novo) | Layout único da planilha: abas, colunas, chaves da aba Geral, listas fechadas, `VERSAO_MODELO = 0.3.0` e o marcador `A_PREENCHER`. |
| `config_xlsx_modelo.py` (novo) + `scripts/gerar_modelo_config.py` | Geram o modelo da calibração (com `A_PREENCHER`) ou migram um perfil YAML (`--migrar`). Validações de lista, proteção das abas Geral, Filtros e Listas e da área de parâmetros da Palavras_chave. A senha só vai pela linha de comando (`--senha`). |
| `config_xlsx.py` (novo) | `ler_configuracao_xlsx()` copia o arquivo para uma pasta temporária, converte cada aba no formato atual do dicionário e devolve uma `ErroCelula(aba, linha, coluna, mensagem)` por problema. |
| `config.py` | `carregar()` mescla `settings.yaml` → perfil → xlsx, mas só nos perfis com `configuracao_xlsx.obrigatoria: true`. `Config.erros_xlsx` entra no `validar()`. `yaml_referenciado` consulta `_inline`. Novas funções `raiz_aplicacao()`, `raiz_recursos()` e `perfil_padrao()` (o .exe usa `calibracao`). Com `TESTE`, os destinatários permitidos são montados como destino padrão + AVISO_ERRO. Validações novas: destino das respostas, ação manual e regras fixas da calibração (IA, TESTE, escritórios, arquivamento). |
| `perfis/calibracao.yaml` (novo) | Seção 4.3, mais `marcar_nao_fornecedores: false`, `pular_ja_respondidos: true`, `acao_manual: CATEGORIZAR` e `arquivamento.raiz: arquivo`. |
| `filtros.py` | `ler_planilha_escritorios()` gera o mapa `MapaEscritorios` (domínio → escritório). Erros claros para arquivo ausente, bloqueado ou só na nuvem, aba ou coluna ausente e domínio repetido com escritórios diferentes (com as linhas). Avisa domínios públicos. |
| `caixa/base.py` | `ErroSeguranca` e `TravaDestinatarios`. Parâmetros novos: `ler_pendentes(aceitar_remetente)`, `responder(redirecionar_para, prefixo_assunto)` e `finalizar(marcar_lido)`. Métodos novos `arquivar()` e `localizar()`. |
| `caixa/outlook_com.py` | Filtro de remetente na varredura; `PR_LAST_VERB_EXECUTED`; resposta de teste (remove todos os destinatários do último para o primeiro, `To = destino`, sem CC/BCC). **Trava em `_concluir()`**: relê `Recipients` em SMTP antes do `Send`/`Save`; endereço não identificado bloqueia; mensagem abortada é descartada (`Close(olDiscard)`). `SaveAs(caminho, olMSG)`. |
| `caixa/arquivo.py` | O mesmo comportamento na caixa simulada, incluindo o modo sem mover. |
| `ciclo.py` | Planilha de escritórios relida a cada ciclo; se falhar, o ciclo não roda e sai um aviso por dia. Leitura sem tocar em e-mails de não fornecedores; e-mail já tratado pelo analista vai para Ignorados. Envio de teste; status por e-mail (CONCLUIDO se saiu, SIMULADO se é rascunho); envio só com modo REAL, categoria liberada e categoria não bloqueada. Categoria desativada ou configurada como MANUAL vai para manual. FORMS_PO sem link vai para manual. `RESPONDER_TEXTO`. Arquivamento .msg. Bloqueio automático por "Tutorial errado". |
| `respostas.py` + modelos | Textos da aba Textos (escapados, um `<p>` por linha, links clicáveis); AVISO_AUTOMATICO, ASSINATURA e NOTA_MANUAL; um `.j2` em `modelos\` ao lado do .exe substitui o padrão; faixa com `{destinatario_original}`. Modelos novos: `TEXTO`, `aviso_falha_ciclo` e `aviso_bloqueio`. O rodapé "Resposta automática · protocolo", que impede o laço, foi mantido. |
| `arquivamento.py` (novo) | Caminho `<raiz>\<Escritório>\<AAAA-MM>\<data>_<protocolo>_<assunto>.msg`. Remove caracteres inválidos, limita o assunto a 60 caracteres e o caminho a 240. Uma falha grava `FALHA: …` e não interrompe o tratamento. |
| `registro.py` | Colunas novas, em lista própria (`COLUNAS_V030`): escritório, destinatário original, destino das respostas, enviado, categoria liberada, arquivado em, máquina, usuário e versão. Tabelas `retorno_manual` e `avisos`; coluna `ciclos.nao_fornecedores`. Planilha de controle: lê o retorno antes de regerar, sem apagar com célula vazia; aba protegida com só o retorno editável, validações e Resumo por categoria. |
| `verificacao.py` (novo) + `__main__.py` | Itens da seção 7.2 no `verificar`, salvo em `logs\verificar_*.txt`. Comandos `arquivar-pendentes` e `menu`; duplo clique no .exe abre o menu. |
| `rpa_duvidas.spec`, `build_exe.bat`, `scripts/rpa_exe.py`, `scripts/gravar_versao.py`, `requirements-build.txt`, `.gitattributes` | Build onedir em 5 passos (`.bat` em CRLF). |

## 3. Desvios em relação à especificação

| Item da especificação | O que foi feito | Motivo |
| --- | --- | --- |
| 4.2 cita `classificacao.arquivo_palavras_chave` | Mantida a chave `classificacao.arquivo_termos` | É o nome usado no código; trocar quebraria os perfis existentes. |
| 5 "linha 1 é o cabeçalho" | Palavras_chave com cabeçalho na linha 4 | Decisão 5 acima: a seção 5.4 coloca os parâmetros no topo. |
| 5.8 lista "Marcadores do próprio RPA" | Dois tipos na aba Filtros: `MARCADOR_ASSUNTO_RPA` e `MARCADOR_TEXTO_RPA` | O `settings.yaml` separa os marcadores de assunto dos marcadores de texto da última mensagem. |
| 5.9 "o analista recebe um aviso de erro" | Aviso no máximo uma vez por dia para o mesmo erro | Senão sairia um aviso a cada 15 minutos. |
| 5.3 "Data da liberação" | Obrigatória quando "Liberada para envio = S" | Sem a data, o bloqueio automático (6.7) não tem referência. |
| 5.6 "Link do formulário obrigatório para FORMS_PO" | `A_PREENCHER` é erro; vazio é aviso, e a FORMS_PO é tratada como MANUAL | A própria 5.6 define o caso do link vazio. |
| 6.5 retorno "por protocolo" | O retorno aparece em todas as linhas do protocolo. Na leitura vale o último valor preenchido, com WARNING se houver conflito. | Um protocolo pode ter mais de um evento (erro e depois reprocessamento). |
| 6.5 Resumo "erros graves" | Erros graves = "Tutorial errado" + "Deveria encaminhar". Coluna informativa para o critério da seção 12.8. | A especificação não define "erro grave". |
| 6.7 bloqueio | Calculado a cada ciclo a partir do retorno já gravado no SQLite (lido no fim do ciclo anterior); vale a partir da data da liberação (inclusive) | O retorno é lido na exportação, no fim do ciclo. |
| 8 colunas novas | Ficaram em `COLUNAS_V030`, separadas de `COLUNAS_EVENTO` | Assim o teste de migração da v0.2.x continua passando sem mudança. |
| `.gitignore` da base | `dados/` virou `/dados/` | O padrão antigo escondia `tests/dados/massa_emails_sintetica.csv`, a massa dos testes. |

## 4. Testes

Os 239 testes da v0.2.1 passam sem alteração. Os testes novos estão em `tests/test_v030_t02` a `test_v030_t15`. O COM do Outlook é sempre simulado (`tests/fakes_outlook.py`), com `To`, `CC`, `BCC` e `Recipients` sincronizados e um destinatário escondido que `Remove()` não tira, para simular o risco da seção 11.

| Critério de aceite | Teste dedicado |
| --- | --- |
| 2 – planilha com erro não lê e-mail | `test_v030_t14_verificar_menu.py::test_criterio_2_*` |
| 3 – nada sai fora do destino padrão / AVISO_ERRO | `test_v030_t07_envio_teste.py::test_criterio_3_*` (64 combinações) |
| 4 / 5 – terceiros intactos / já respondidos | `test_v030_t06_caixa_pessoal.py` |
| 6 – .msg ou FALHA | `test_v030_t11_arquivamento.py` |
| 7 – retorno sobrevive às regenerações | `test_v030_t12_retorno_manual.py` |
| 8 – categoria não liberada = rascunho | `test_v030_t08_envio_por_categoria.py` |
| 9 – IA nunca chamada | `test_v030_t14_verificar_menu.py::test_criterio_9_*` |

## 5. Pendente

- **T15:** build real com PyInstaller no Windows 64 bits e teste em uma máquina sem Python (antivírus e SmartScreen).
- **T16:** revisão deste guia (docs/12) pelo financeiro e o PDF `LEIA-ME_Instalacao.pdf`.
- **T17:** instalação assistida (fora do escopo desta entrega).
- **Ensaio real:**
  - trava com destinatários internos do M365 (endereços EX → SMTP);
  - `SaveAs` .msg e `PR_LAST_VERB_EXECUTED`;
  - tipo da conta;
  - prévia em uma caixa real sem alterar e-mails de terceiros;
  - planilha de controle no SharePoint sendo editada pela outra analista (risco de cópia de conflito do OneDrive).
