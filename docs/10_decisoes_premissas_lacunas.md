# 10 · Decisões, premissas e lacunas

## 1. Decisões de projeto

| ID | Decisão | Motivo | Rever quando |
|---|---|---|---|
| D01 | Desenvolver na **caixa individual** do desenvolvedor, numa **subpasta dedicada** (`@inbox/RPA_Teste`), e migrar para a caixa oficial só pela configuração | Começar sem esperar a TI sem arriscar a Caixa de Entrada real | Entrega da conta de serviço (S03) |
| D02 | Respostas automáticas vão para uma **4ª pasta, `Ignorados`**, sem encaminhar | A especificação manda ignorá-las, mas também diz que todo e-mail termina num destino. Encaminhar ausências aos analistas só gera ruído | Validar com a área. Para manter só 3 pastas, aponte `pastas_destino.ignorados` para a pasta Encaminhados |
| D03 | Responder com **`Reply()` + analistas em CC** em vez de `ReplyAll()` | Evita copiar destinatários que o fornecedor incluiu (outros fornecedores, a própria caixa) | Configurável: `respostas.responder_todos` |
| D04 | **Caixa simulada em disco** com a mesma interface do Outlook | Testar e demonstrar o ciclo inteiro sem Outlook e sem e-mail real | — |
| D05 | **SQLite** como fonte da verdade e planilha `.xlsx` gerada a partir dele | A planilha pode estar aberta no Excel; o banco garante idempotência e histórico sem perda | Se a área quiser outro formato de controle |
| D06 | Gravar `EM_ANDAMENTO` **antes** de enviar e `acao_executada` **logo depois** | Se o ciclo cair no meio, o e-mail vai para Erro para conferência humana, em vez de ser respondido de novo | — |
| D07 | **Trava de destinatários** obrigatória fora de prod | Impede que um teste chegue por engano a um fornecedor | — |
| D08 | **Limite de confiança inicial 0,70** | Conservador: o erro grave pesa mais (seção 4 da especificação). Com 0,55 apareceu 1 erro grave na massa sintética | Calibração com a massa real (S01) |
| D09 | Categorias especiais `MANUAL_SAP` e `MANUAL_FORA_ESCOPO` no classificador | Dúvidas que **parecem** mapeáveis, mas dependem do SAP ou são cadastro novo, precisam ir para manual com o motivo certo | — |
| D10 | Tutorial que existe **só na nuvem** (OneDrive) é tratado como indisponível | A especificação avisa que o anexo falha nesse caso | `exigir_arquivo_local: false` se a TI garantir o download |
| D11 | Chave de idempotência = **Internet Message-ID** (com EntryID como alternativa) | O EntryID pode mudar quando o item é movido; o Message-ID não | — |
| D12 | Faixa visível "AMBIENTE DE TESTE / DEMONSTRAÇÃO" nas mensagens geradas fora de prod | Nenhum rascunho de teste pode ser confundido com resposta oficial | — |
| D13 | Comando `previa` (classifica sem agir) | Validar decisões com os analistas antes de qualquer rascunho | — |

## 2. Premissas (não estão na especificação)

| ID | Premissa |
|---|---|
| P01 | A máquina do desenvolvedor tem **Outlook clássico** (o novo Outlook não suporta COM). Se não tiver, F03 fica bloqueada nessa máquina. |
| P02 | Em dev, os "fornecedores" são o próprio desenvolvedor e colegas, com e-mails internos. Nenhum e-mail sai para fora do domínio. |
| P03 | O piloto continua em pywin32 numa VM; o Microsoft Graph é só para a produção definitiva (seção 5 da especificação). |
| P04 | A planilha de controle é local (`dados/<perfil>/`). O local definitivo será definido com a área. |
| P05 | A massa real terá de 10 a 20 exemplos por categoria; a especificação não fixa a quantidade. |
| P06 | Os textos de resposta atuais são provisórios e foram redigidos pela equipe técnica; não foram aprovados pela área. |
| P07 | Os nomes de subpasta e os padrões de arquivo dos tutoriais seguem a pasta de rede atual e mudam quando os tutoriais forem publicados no SharePoint. |
| P08 | Python 3.10+ está disponível (ou pode ser instalado) nas máquinas de dev e na VM. |

## 3. Lacunas a esclarecer

| ID | Dúvida | Impacta | Com quem |
|---|---|---|---|
| L01 | **Cenário 2:** como o retorno do fornecedor à lista de temas será associado ao e-mail original (mesmo fio? quantas tentativas antes de mandar para manual?) | F09 | Área |
| L02 | **E-mail com vários temas:** encaminhar para manual (comportamento atual, por baixa confiança), responder ao tema principal ou enviar mais de um tutorial? | F06, F12 | Área |
| L03 | **Destino do manual por motivo:** como o robô distingue "tributário" de "demais matérias"? Hoje existe `por_motivo` (SAP, FORA_DO_ESCOPO…), mas não um motivo "tributário" | F13 | Área |
| L04 | **Aviso de erro:** e-mail para a caixa dos analistas é suficiente? Outro canal? | F16 | Área |
| L05 | **IA com dados sintéticos** durante o desenvolvimento é permitida antes da aprovação formal? | F08 | Segurança |
| L06 | **Planilha de controle:** onde fica, quem acessa e por quanto tempo é guardada (contém remetente e assunto, sujeita à LGPD)? | F15 | Área / Segurança |
| L07 | **Janela de execução:** horário comercial ou 24h? Intervalo de 15 min é adequado? | F17 | Área |
| L08 | **Limite de anexo** da organização e formato dos tutoriais (PPT × PDF) | F10 | TI / Área |
| L09 | **Repositório de código** e versionamento (Azure DevOps, GitHub corporativo, pasta de rede?) | Todas | Área BT |
| L10 | **Resposta automática em Ignorados** (D02) atende, ou a área prefere receber essas mensagens? | F05 | Área |

> **v0.2.0:** L02 corresponde ao PA06 e L05 ao PA08 da especificação funcional de 22/10/2026 (seção 5 abaixo). Os dois continuam abertos.

## 4. Decisões de implementação – v0.2.0 (classificação por IA)

Pontos que a especificação funcional (22/10/2026) não fecha ou em que duas regras dela se cruzam. Regra adotada: **na dúvida, a opção mais conservadora (encaminhar para manual)**.

| ID | Decisão de implementação | Motivo |
|---|---|---|
| DI01 | **V5 confere só o domínio** do `tutorial` (código de tutorial conhecido ou `null`). A coerência com a categoria fica com a **D7** (manual `EXCECAO`, sem nova chamada) | A seção 6.5 manda tratar "tutorial incoerente" com a D7 e "não corrigir". As duas leituras levam a manual; esta evita uma chamada extra |
| DI02 | **V9:** `resumo_duvida` vazio num caso manual é **aceito** com o resumo padrão; resumo com mais de 400 caracteres **é rejeitado** (nova chamada) | A seção 6.5 trata o resumo vazio explicitamente; o limite de tamanho continua sendo V9 |
| DI03 | Se a **chamada de correção** falhar por timeout/erro, o e-mail vai para manual com `RESPOSTA_IA_INVALIDA` (a 1ª resposta já era inválida) e **não** conta para o limite de falhas seguidas | Conservador: manual. O contador de falhas mede indisponibilidade, e a IA respondeu |
| DI04 | **Falhas seguidas** (RNF-IA03) contam só e-mails que terminaram em `IA_INDISPONIVEL` por falha de chamada; qualquer resposta recebida zera o contador; o contador volta a zero a cada ciclo | A especificação fala em "falhas" da IA, não em respostas mal formatadas |
| DI05 | Motivo **`CATEGORIA_SEM_TUTORIAL`** incluído em `MotivoManual` (é citado na E5, mas não na lista da RN7.1). Ele é avaliado logo depois da D1 | Um código válido sem entrada em `categorias_ia.yaml` não pode ser respondido |
| DI06 | **D2** generalizada: "categoria com `tutorial: null` em `categorias_ia.yaml`", com o motivo vindo do próprio YAML (C07 → `SEM_RESPOSTA_PADRAO`, C99 → `NAO_IDENTIFICADO`) | Com a configuração inicial é exatamente a regra da especificação; evita lista fixa no código |
| DI07 | O **limite 0,80** fica em `classificacao.ia.limite_confianca` e vale automaticamente quando `tipo: ia` (`Config.limite_confianca`). A D3 usa o mesmo valor que o ciclo já aplicava | Trocar o tipo restaura o 0,70 sem editar outra chave (RNF-IA08) |
| DI08 | A **sugestão da RN2.4** (chamar a IA só para resumir e-mails de fora da lista) **não** foi implementada: FORA DA LISTA continua sem IA, como na v0.1.0 | Depende do PA09; não chamar a IA também evita enviar dados de remetentes desconhecidos |
| DI09 | Filtros de **e-mail interno e spam vêm desligados** (lista vazia / `ativo: false`). Ligados só no perfil `demo_ia`. Em `dev` o interno fica vazio de propósito; em `prod` pede `<PREENCHER-dominio-corporativo>` | Mantém a v0.1.0 igual com `palavras_chave`; em dev os testes vêm do domínio interno |
| DI10 | E-mail interno inclui **subdomínios** e a própria caixa (`caixa.conta`, `caixa.enviar_em_nome_de`, quando são endereços). O motivo vai para a coluna "Motivo" com o prefixo `INTERNO`/`SPAM` (`Resultado.motivo_ignorado`) | RN2.2; não é motivo de manual |
| DI11 | **Mascaramento:** qualquer sequência de 14 dígitos (com ou sem pontuação) vira `[CNPJ]`, sem conferir dígito verificador; 11 dígitos colados viram `[CPF]` se o DV confere, senão `[TELEFONE]`; o rótulo bancário (agência, conta, c/c, banco) é mantido e só o número vira `[BANCO/AG/CC]`; PIX só é mascarado quando o valor tem dígito ou `@`. Assunto, corpo, nomes de anexos e histórico são mascarados. Números de NF e pedido **não** (não estão na RN3.1) | Na dúvida, mascarar: um número a mais escondido não prejudica a classificação |
| DI12 | **Truncamento** (RN3.2) mantém o total dentro do limite, já contando o marcador ` [...]` | Respeita o limite de custo (RNF-IA09) |
| DI13 | Montagem do prompt em **uma única passada**; `<<<` e `>>>` dentro do e-mail viram `<<`/`>>`; anexos/histórico vazios viram `(nenhum)` (como nos exemplos do Anexo A) | Impede que o conteúdo feche os delimitadores ou injete marcadores (RNF-IA05 / R11) |
| DI14 | `historico_resumido` = texto a partir do 1º marcador de histórico, extraído **antes** da remoção estrutural do HTML (com fallback pela diferença), até 2.000 caracteres; antes da IA ele é mascarado e truncado de novo | RN1.1: o histórico é só contexto |
| DI15 | Provedor **`http_generico`**: formato de requisição/resposta todo no `settings.yaml` (valores de exemplo no padrão *chat completions*). Timeout e erro HTTP/conexão → novas tentativas; credencial ausente → sem nova tentativa. No log vai só o código do erro | PA08 aberto; nenhum endpoint, chave ou nome de provedor no código |
| DI16 | Provedor **`simulado`** (regras em `config/ia_simulada.yaml`) é o padrão do `settings.yaml`; o `verificar` aponta erro se ele estiver em uso com `tipo: ia` em prod | Nenhuma chamada real por acidente |
| DI17 | Registro: além das colunas da RN8.1, **`regra_decisao` e `hash_prompt`** (RNF-IA02). `respostas_ia` guarda cada resposta bruta (inclusive as inválidas), com nº da chamada e se foi válida, **sem o prompt**. A planilha não inclui `respostas_ia` | Auditoria sem expor o conteúdo do e-mail fora da tabela restrita |
| DI18 | A linha de log da v0.1.0 (com remetente e assunto) foi mantida; a IA ganhou uma linha própria só com metadados | Compatibilidade; a RN8.2 proíbe corpo, prompt e resumo |
| DI19 | **Aviso de falhas seguidas** usa o modelo novo `aviso_ia_indisponivel.html.j2`, assunto em `classificacao.ia.assunto_alerta`, para `destinatarios.avisos_erro`, passando pela trava de destinatários | Texto de negócio fora do código |
| DI20 | `correcoes_formato` é limitado a **1** no código, qualquer que seja o valor configurado | E4: "no máximo 1 nova chamada" |
| DI21 | V1: JSON válido que não é objeto (ex.: lista) → procura o primeiro objeto `{...}` dentro dele e marca `formato_corrigido`. Duplicidades em secundárias/sinais são removidas sem rejeitar | Seção 6.5 |
| DI22 | Na nota ao analista, "Sugestão do classificador" mostra o **código C** e a confiança da IA; a categoria do .docx aparece com a descrição do `categorias_ia.yaml` | RN7.2 |
| DI23 | `avaliar_classificador.py` com IA: consulta a IA **uma vez** por e-mail e reaplica D1–D7 para cada limite. A massa continua com `categoria_esperada` no vocabulário do robô (`TUT_*`, `FORMS_PO`, `MANUAL`) | Calibração sem multiplicar custo. **Atenção:** a massa sintética tem `TUT_CONNECT` e `FORMS_PO`, que não existem na taxonomia da IA (PA02/PA05), e o provedor simulado não é IA – os números dele não medem nada |
| DI24 | Perfil novo **`demo_ia`** (caixa simulada + IA simulada + filtro interno) e `preparar_demo.py --ia` | Demonstrar E1–E8 sem tocar no perfil `demo` usado pelos testes antigos |

## 5. Pontos em aberto da especificação funcional (PA01–PA17)

Nenhum foi resolvido pela v0.2.0. A coluna "Onde ajustar" mostra o que muda quando cada um for decidido.

| ID | Ponto | Situação na v0.2.0 | Onde ajustar |
|---|---|---|---|
| PA01 | Taxonomia completa (C01, C04, C08, C09, C11) | Não usados; a IA marca a dúvida extra como C99 | Nova versão do prompt + `categorias_ia.yaml` |
| PA02 | Categoria de acesso ao Connect | Fora: e-mails de acesso caem em C99 → manual. `TUT_CONNECT` segue só no classificador por palavras-chave | Prompt v2 + `categorias_ia.yaml` |
| PA03 | Reembolso antes da aprovação? | **C06 desligada** (`resposta_automatica: false` → D6) | `categorias_ia.yaml` → `C06.resposta_automatica` |
| PA04 | Resposta padrão para C07 | C07 sempre manual (D2) | `categorias_ia.yaml` + modelo `.html.j2` |
| PA05 | PO dentro de C03: Forms ou manual? | Manual (`PEDIDO_PO` → D5). `FORMS_PO` só no classificador por palavras-chave | Regra nova na decisão |
| PA06 | Resposta parcial com múltiplas dúvidas (L02) | Versão 1: qualquer secundária → manual (D4) | `decisao_ia.decidir` (mudança M3) |
| PA07 | Tutorial de desbloqueio ≠ atualização | Usa `TUT_CADASTRO` | `tutoriais.yaml` / `categorias_ia.yaml` |
| PA08 | **Provedor de IA corporativa** (endpoint, modelo, limites, retenção, dados reais × sintéticos – L05) | **Bloqueante para ligar a IA.** Só existe o provedor simulado | `classificacao.ia.provedor.http_generico` + credencial `ia_api_key` |
| PA09 | Destino de internos e fora da lista; resumo dos de fora | Interno → Ignorados (desligado por padrão); fora da lista → manual sem IA (DI08) | `filtros.dominios_internos`; `ciclo._tratar` |
| PA10 | Spam pelo SCL? | Implementado, **desligado** | `filtros.spam.ativo` |
| PA11 | Inconsistência no .docx (3 × 4 "Sem resposta") | Sem impacto no código | — |
| PA12 | Taxonomia C substitui a do `Entrega3_Prompt_Classificacao_IA.md`? | Implementado só o prompt do Anexo A (`classificacao_v1`) | — |
| PA13 | Novo cadastro | Cai em C99 → manual | Prompt v2, se mudar |
| PA14 | Retenção/acesso de `respostas_ia` e da planilha com resumo (L06) | Tabela criada no `estado.db` local; sem expurgo automático | `registro.py` (rotina de retenção a definir) |
| PA15 | Massa para calibrar o limite (≥ 20 por categoria) | Ferramenta pronta (`--limites`); limite inicial 0,80 | `classificacao.ia.limite_confianca` |
| PA16 | Pastas PEP e Now/E-mail fora da amostra | Sem impacto até a amostra crescer | Prompt / categorias |
| PA17 | Textos dos modelos `TUT_*.html.j2` provisórios (P06) | Sem mudança | `config/modelos/` |
