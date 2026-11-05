# 09 · Rastreabilidade de requisitos

Requisitos da especificação de 15/10/2026 (seções 1–4) e da especificação funcional da classificação por IA de 22/10/2026 (seções 5–8, v0.2.0) → implementação → teste → status.

Legenda: ✅ atendido e testado · ⚠️ atendido com dado simulado / falta validação real · ⛔ bloqueado

## 1. Requisitos funcionais

| ID | Requisito (resumo) | Implementação | Testes | Status |
|---|---|---|---|---|
| RF01 | Ler os não processados da caixa, em ciclos com intervalo configurável | `CaixaEmail.ler_pendentes`, `caixa.lote_maximo`, `execucao.intervalo_minutos`, `--loop`, Agendador | `test_ciclo`, `test_outlook_com::test_ler_somente_nao_lidos` | ⚠️ COM a validar no Outlook (M1–M2) |
| RF02 | Extrair remetente, assunto, corpo limpo, data, ID e anexos (só registrados) | `outlook_com._converter`, `extracao.html_para_texto`, `limpar_corpo` | `test_extracao`, `test_outlook_com::test_leitura_*` | ✅ / calibrar com e-mails reais |
| RF03 | Ignorar respostas automáticas e já processados; fora da lista → manual | `extracao.detectar_resposta_automatica`, `Registro.estado`, `ListaFornecedores` | `test_extracao::test_detectar_*`, `test_ciclo::test_idempotencia*` | ⚠️ lista oficial pendente (S06) |
| RF04 | Categoria + confiança; abaixo do limite → MANUAL | `ClassificadorPalavrasChave`, `ciclo._tratar` | `test_classificacao`, `test_ciclo::test_baixa_confianca*` | ⚠️ termos sem massa real (S01) |
| RF05 | Resposta a partir de modelo por categoria, no mesmo fio, analistas em cópia | `GeradorRespostas`, `CaixaEmail.responder` (`Reply` + CC) | `test_tutoriais_respostas`, `test_ciclo::test_cada_caminho*` | ⚠️ textos provisórios (S09) |
| RF06 | Localizar o tutorial, validar existência e tamanho, anexar; falha → erro | `RepositorioTutoriais.localizar` | `test_tutoriais_respostas`, `test_ciclo::test_tutorial_ausente*` | ⚠️ tutoriais fictícios (S05) |
| RF07 | Link do Forms no corpo, sem anexo | `FORMS_PO.html.j2`, `respostas.link_forms_po` | `test_resposta_forms_traz_o_link` | ⚠️ link real (S07) |
| RF08 | Encaminhar para análise manual com o motivo no assunto | `ciclo._encaminhar_manual`, `prefixo_manual`, `destino_manual(motivo)` | `test_ciclo::test_cada_caminho*` | ⚠️ destinos reais (S08) |
| RF09 | Marcar lido, aplicar categoria do Outlook, mover para Respondidos/Encaminhados/Erro | `CaixaEmail.finalizar` | `test_outlook_com::test_responder_em_rascunho*` | ✅ (+ pasta Ignorados, ver D02) |
| RF10 | Uma linha por e-mail: data, remetente, assunto, categoria, confiança, ação, arquivo, status, erro | `Registro.gravar`, `exportar_planilha` | `test_ciclo::test_registro_e_planilha` | ✅ |
| RF11 | Modo de teste: classifica e monta como rascunho, sem enviar | `execucao.envio_real=false` → `Save()` | `test_ciclo`, `test_outlook_com` | ✅ |

## 2. Requisitos não funcionais

| ID | Requisito | Implementação | Testes | Status |
|---|---|---|---|---|
| RNF01 | Nunca responder duas vezes | Tabela `estado`: `EM_ANDAMENTO` antes do envio e `acao_executada` logo depois; reconciliação | `test_idempotencia*`, `test_falha_ao_mover*` | ✅ |
| RNF02 | Erro num e-mail não interrompe o ciclo; vai para Erro e avisa | `ciclo._tratar_com_protecao`, `_registrar_erro`, `aviso_erro.html.j2` | `test_erro_vai_para_pasta_erro*` | ✅ |
| RNF03 | Log técnico diário + planilha de controle | `configurar_log`, `exportar_planilha` | `test_registro_e_planilha` | ✅ |
| RNF04 | Credenciais fora do código; IA só com serviço aprovado | `segredos.py` (keyring/variável); IA com provedor configurável (`http_generico`) e credencial via `segredos.obter()` | `test_nenhum_endereco_fixo_no_codigo`, `test_classificador_ia::test_http_generico_*` | ✅ / provedor ⛔ (PA08 / S02) |
| RNF05 | ≈ 50 e-mails/dia, picos no início/fim do mês | Lote configurável, ciclo de segundos por e-mail, trava contra sobreposição | — | ⚠️ volume a confirmar (S13) |
| RNF06 | Responder no mesmo ciclo | Leitura → resposta → mover no mesmo ciclo | `test_ciclo` | ✅ |
| RNF07 | Termos, modelos, caminhos, link e destinatários só na configuração | `config/` + teste anti-hardcode | `test_config` | ✅ |
| RNF08 | Chave liga/desliga envio real | `execucao.envio_real` | `test_envio_real_marca_concluido` | ✅ |

## 3. Critérios de aceite do MVP (seção 9)

| Critério | Situação |
|---|---|
| 100% dos e-mails lidos têm registro e terminam em Respondidos, Encaminhados ou Erro | ✅ automatizado (`test_cada_caminho*`); resposta automática vai para Ignorados (D02) |
| Cada categoria de tutorial envia o arquivo correto; `FORMS_PO` envia o link correto | ⚠️ com arquivos fictícios; repetir com o SharePoint |
| Resposta no mesmo fio, com os analistas em cópia | ⚠️ validado com objetos simulados; validar no Outlook (M2) |
| Fora do escopo (inclusive SAP) encaminhado com o motivo | ✅ |
| Nenhum e-mail respondido duas vezes | ✅ |
| Termos, modelos, caminhos e link mudam só na configuração | ✅ |

## 4. Etapas do plano de entrega (seção 9)

| Etapa | Situação |
|---|---|
| 1. Caixa de e-mail | ✅ implementada; falta o teste na caixa individual (M1–M10) |
| 2. Respostas (com modo simulação) | ✅ implementada com conteúdo provisório |
| 3. Classificador base | ✅ implementado; calibração aguarda S01 |
| 4. Avaliação da classificação | ⚠️ ferramenta pronta; massa real e protótipos de IA/menu bloqueados (S01, S02, S09) |
| 5. Piloto | ⛔ S03, S04 e demais |

## 5. Classificação por IA – etapas E1 a E8 (v0.2.0)

Fonte: `especificacao_funcional_classificacao.md`, seção 3 e Anexo B. Todos os testes usam o provedor **simulado** e dados fictícios.

| Etapa | Implementação (arquivo → função) | Testes | Status |
|---|---|---|---|
| E1 Leitura e pré-processamento | `extracao.processar` → `extrair_historico`, `truncar`; `html_para_texto(remover_historico=False)`; `modelos.EmailRecebido.historico_resumido` | `test_filtros_extracao_v020::test_historico_resumido_*`, `test_sem_historico` | ✅ |
| E2 Filtros de exclusão | `filtros.FiltroInterno.interno`, `filtros.FiltroSpam.spam`; `ciclo.Robo._tratar` (passo 1b) → `_ignorar`; `__main__.cmd_previa`; alerta de lista vazia em `cmd_verificar` | `test_filtros_extracao_v020::test_filtro_interno`, `test_filtro_spam`, `test_ciclo_ignora_interno_e_spam_sem_chamar_a_ia`; `test_verificar_avaliar::test_verificar_alerta_lista_de_fornecedores_vazia_em_prod` | ✅ (destino final PA09/PA10) |
| E3 Chamada à IA | `mascaramento.mascarar/preparar_para_ia`; `classificacao/ia.py` → `ModeloPrompt.montar`, `ClassificadorIA.montar_prompt/_chamar/consultar`; `provedores_ia.ProvedorSimulado/ProvedorHttpGenerico`; `classificacao/__init__.criar_classificador` (tipo `ia`) | `test_mascaramento` (todos); `test_classificador_ia::test_timeout_*`, `test_prompt_*`, `test_conteudo_do_email_nao_fecha_delimitadores*`, `test_http_generico_*`, `test_5_falhas_seguidas_*` | ⚠️ provedor real pendente (PA08) |
| E4 Validação | `classificacao/validacao_ia.py` → `extrair_json`, `validar_objeto`, `validar_resposta`; correção de formato em `ClassificadorIA.consultar` | `test_validacao_ia` (todos); `test_classificador_ia::test_json_invalido_*`, `test_cerca_markdown_*` | ✅ |
| E5 Decisão | `classificacao/decisao_ia.py` → `CategoriasIA.de_dict`, `decidir`; `config/categorias_ia.yaml`; `Config.limite_confianca` (0,80 com `tipo: ia`) | `test_decisao_ia` (todos); `test_anexo_a::test_exemplo_passa_na_validacao_e_na_decisao` | ✅ (limite a calibrar – PA15) |
| E6 Resposta com tutorial | Sem mudança: `ciclo._responder_tutorial`, `tutoriais.localizar`, `respostas.resposta` | `test_ciclo_ia::test_ciclo_ia_responde_com_tutorial_e_encaminha_com_resumo` (texto da IA não vai ao fornecedor) | ✅ (textos provisórios – PA17) |
| E7 Encaminhamento com resumo | `respostas.GeradorRespostas.nota_manual` + `encaminhamento_manual.html.j2` (alterados juntos – R6); `modelos.MotivoManual`; `settings.yaml → respostas.rotulos_motivo_manual` | `test_ciclo_ia::test_ciclo_ia_responde_*`, `test_ia_indisponivel_vai_para_manual_e_nao_para_erro`; `test_tutoriais_respostas::test_nota_manual_e_aviso` (compatibilidade) | ✅ |
| E8 Registro e log | `registro.COLUNAS_EVENTO`, `migrar`, `Registro.gravar` (tabela `respostas_ia`), `exportar_planilha`; `ciclo._apos_classificacao_ia` (log sem corpo/prompt/resumo) | `test_registro_migracao` (todos); `test_ciclo_ia::test_ciclo_ia_responde_*` (RN8.2), `test_json_invalido_persistente_no_ciclo` | ✅ (retenção PA14) |

## 6. Regras de decisão D1 a D7 (seção 6.1)

Implementadas em `classificacao/decisao_ia.decidir`, nesta ordem.

| Regra | Condição → resultado | Testes |
|---|---|---|
| D1 | Falha ou resposta inválida → `IA_INDISPONIVEL` / `RESPOSTA_IA_INVALIDA` | `test_decisao_ia::test_d1_falha_da_ia`, `test_d1_sem_resposta_e_sem_motivo_vira_invalida`; `test_classificador_ia::test_timeout_faz_2_novas_tentativas_*`, `test_json_invalido_persistente_*`; `test_ciclo_ia::test_ia_indisponivel_*` |
| (E5) | Código sem mapeamento → `CATEGORIA_SEM_TUTORIAL` | `test_decisao_ia::test_e5_codigo_sem_mapeamento` |
| D2 | C07 / C99 → `SEM_RESPOSTA_PADRAO` / `NAO_IDENTIFICADO` | `test_decisao_ia::test_d2_categoria_sem_tutorial`; `test_anexo_a` (exemplos 8 e 9) |
| D3 | Confiança < limite (0,80) → `BAIXA_CONFIANCA` | `test_decisao_ia::test_d3_baixa_confianca` |
| D4 | Dúvida secundária → `MULTIPLAS_DUVIDAS` | `test_decisao_ia::test_d4_multiplas_duvidas`; `test_anexo_a` (exemplos 2, 5 e 7) |
| D5 | Sinal de exceção → `EXCECAO` | `test_decisao_ia::test_d5_sinal_de_excecao`; `test_anexo_a` (exemplo 3) |
| D6 | Categoria desabilitada (C06) → `CATEGORIA_DESABILITADA` | `test_decisao_ia::test_d6_categoria_desabilitada`; `test_anexo_a` (exemplo 6) |
| D7 | IA sugere manual ou tutorial ≠ o da categoria → `EXCECAO` | `test_decisao_ia::test_d7_ia_sugere_manual`, `test_d7_tutorial_diferente_do_da_categoria` |
| — | Nenhuma → `RESPONDER_TUTORIAL` | `test_decisao_ia::test_resposta_automatica_quando_nenhuma_regra_barra`; `test_anexo_a` (exemplos 1 e 4) |
| Ordem | D2 → D3 → D4 → D5 | `test_decisao_ia::test_ordem_das_regras_*` |

## 7. Requisitos não funcionais da IA (seção 7)

| ID | Implementação | Testes | Status |
|---|---|---|---|
| RNF-IA01 Log | `ciclo._apos_classificacao_ia`: protocolo, categoria, confiança, regra, ação, motivo, latência, tentativas e tokens | `test_ciclo_ia::test_ciclo_ia_responde_*` | ✅ |
| RNF-IA02 Auditoria | Versão + hash do prompt, modelo, data/hora, regra, JSON bruto (`respostas_ia`) | `test_registro_migracao::test_gravar_evento_da_ia_*`; `test_anexo_a::test_prompt_identico_ao_anexo_a` | ✅ |
| RNF-IA03 Falhas | Timeout 30 s, 2 novas tentativas (2 s/4 s), 5 falhas seguidas → aviso único + IA desligada no ciclo | `test_classificador_ia::test_timeout_*`, `test_5_falhas_*`, `test_sucesso_zera_*`; `test_ciclo_ia::test_5_falhas_*` | ✅ |
| RNF-IA04 Dados sensíveis | `mascaramento.py`; original ao analista sem máscara | `test_mascaramento`; `test_classificador_ia::test_prompt_mascarado_*`; `test_ciclo_ia` (CNPJ no encaminhamento) | ⚠️ retenção/provedor (PA08, PA14) |
| RNF-IA05 Segurança do prompt | Delimitadores, substituição em uma passada, `<<<`/`>>>` neutralizados, listas fechadas, decisão pelo RPA, texto da IA nunca ao fornecedor | `test_classificador_ia::test_conteudo_do_email_nao_fecha_*`; `test_ciclo_ia::test_ciclo_ia_responde_*` | ✅ |
| RNF-IA06 Desempenho | Processamento sequencial; latência registrada | — | ⚠️ medir com o provedor real |
| RNF-IA07 Qualidade | `scripts/avaliar_classificador.py --classificador ia --limites ...` | `test_verificar_avaliar::test_avaliar_*` | ⚠️ massa real (PA15) |
| RNF-IA08 Reversibilidade | `classificacao.tipo: palavras_chave` volta ao F06 e ao limite 0,70 | `test_ciclo_ia::test_reversibilidade_*`; os 81 testes da v0.1.0 sem ajuste | ✅ |
| RNF-IA09 Custo | Truncamento, 1 chamada (+1 só na correção), tokens registrados | `test_classificador_ia::test_json_invalido_persistente_*` (máximo 2 chamadas) | ✅ |
