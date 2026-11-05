# 03 · Configuração

Regra do projeto: **nenhum endereço, pasta, credencial ou texto de negócio fica no código** (RNF07). Um teste automatizado (`test_nenhum_endereco_fixo_no_codigo`) falha se aparecer um e-mail ou caminho de usuário em `src/`.

## 1. Perfis

```text
config/settings.yaml          base comum a todos
        + config/perfis/<perfil>.yaml   só o que muda
        = configuração efetiva
```

O perfil vem de `--perfil <nome>` ou da variável de ambiente `RPA_PERFIL`. Sem nenhum dos dois, vale `dev`.

| Perfil | Caixa | Pasta lida | Envio real | Uso |
|---|---|---|---|---|
| `demo` | simulada em disco | `dados_teste/caixa_simulada/entrada` | não | Demonstração e testes, sem Outlook |
| `demo_ia` (v0.2.0) | simulada em disco | `dados_teste/caixa_simulada/entrada` | não | Igual ao `demo`, com `classificacao.tipo: ia`, **IA simulada** e filtro de e-mail interno ligado |
| `dev` | sua caixa individual (Outlook COM) | `@inbox` (v0.2.1), só assuntos com `[RPA-TESTE]`, sem mover | não | Desenvolvimento com e-mails de teste |
| `prod` | caixa oficial da automação | `@inbox` | não no piloto; sim após aprovação | Piloto e produção |

Valores marcados com `<PREENCHER...>` impedem a execução. O comando `verificar` lista todos eles.

## 2. Referência de `settings.yaml`

### `caixa`

| Chave | Exemplo | Descrição |
|---|---|---|
| `tipo` | `outlook_com` | `outlook_com`, `arquivo` (simulada) ou `graph` (ainda não implementado) |
| `conta` | `""` | Conta ou caixa no perfil do Outlook (nome exibido ou SMTP). Vazio = conta padrão |
| `pasta_entrada` | `@inbox/RPA_Teste` | Pasta lida. `@inbox` = Caixa de Entrada em qualquer idioma; subpastas separadas por `/` |
| `pastas_destino.respondidos` / `encaminhados` / `erro` / `ignorados` | `@inbox/Respondidos` | Destinos do RF09 |
| `criar_pastas_ausentes` | `true` em dev | Cria as pastas que faltam. Em prod fica `false`, porque as pastas são liberadas pela TI |
| `categorias_outlook.*` | `RPA - Respondido` | Categoria do Outlook aplicada ao e-mail original. `simulado` é usada no modo simulação |
| `ler_todos_da_pasta` | `true` | `false` = só os não lidos |
| `lote_maximo` | `50` | E-mails por ciclo |
| `enviar_em_nome_de` | `""` | Caixa compartilhada: preenche "Em nome de" |
| `mover_apos_tratar` (v0.2.1) | `true` | `false` = modo sem mover: o e-mail fica na pasta de entrada, lido e com a categoria `RPA - …`, e os ciclos seguintes o pulam. Obrigatório com conta Exchange ActiveSync (o `verificar` acusa) |
| `filtro_assunto` (v0.2.1) | `""` | Só lê assuntos que contêm o texto (sem diferenciar maiúsculas). Em dev: `[RPA-TESTE]` |
| `recebidos_desde` (v0.2.1) | `""` | `AAAA-MM-DD`. Ignora e-mails recebidos antes da data |
| `max_varredura` (v0.2.1) | `500` | Quantos e-mails mais recentes examinar por ciclo quando um filtro ou o modo sem mover está ligado |
| `arquivo.raiz` | `dados_teste/caixa_simulada` | Só para `tipo: arquivo` |

### `execucao`

| Chave | Descrição |
|---|---|
| `envio_real` | **Chave geral (RNF08).** `false` = só rascunhos (RF11) |
| `intervalo_minutos` | Intervalo do modo `--loop`; serve de referência para o Agendador |

### `seguranca`

| Chave | Descrição |
|---|---|
| `destinatarios_permitidos` | Domínios (`@empresa.com.br`) ou e-mails. Fora de `prod` é **obrigatório**: qualquer outro destinatário bloqueia a ação e manda o e-mail para Erro |

### `destinatarios`

| Chave | Descrição |
|---|---|
| `analistas_cc` | Em cópia nas respostas (RF05) |
| `analise_manual.padrao` | Destino do encaminhamento (RF08) |
| `analise_manual.por_motivo` | Destino específico por motivo, ex.: `{SAP: [...], FORA_DO_ESCOPO: [...]}` |
| `avisos_erro` | Quem recebe o aviso quando um e-mail cai em Erro (RNF02) |

### `filtros`

| Chave | Descrição |
|---|---|
| `validar_fornecedor` | `true` = remetente fora da lista vai para `[MANUAL – FORA DA LISTA]` |
| `arquivo_fornecedores` | YAML com `emails:` e `dominios:` |
| `assuntos_resposta_automatica` | Trechos de assunto que indicam resposta automática (sem acento, minúsculas) |
| `dominios_internos` (v0.2.0) | Domínios da Companhia (`empresa.com.br` ou `@empresa.com.br`; subdomínios também contam). Remetente interno → **Ignorados** com motivo `INTERNO`, sem chamar a IA (E2 – RN2.2). A própria caixa da automação (`caixa.conta`, `caixa.enviar_em_nome_de`) também conta. Vazio = desligado (padrão; em dev fica vazio de propósito). Destino final em aberto (PA09) |
| `mensagens_do_rpa.*` (v0.2.1) | Proteção contra laço: respostas, encaminhamentos e avisos do próprio robô que voltam para a caixa vão para **Ignorados** com motivo `PROPRIO_RPA`. `assuntos` = regex sobre o assunto sem RE:/ENC:; `textos` = regex sobre a **última** mensagem (antes do histórico). Ligado por padrão |
| `spam.ativo` / `spam.cabecalho` / `spam.limite_scl` (v0.2.0) | Opcional (RN2.3 – PA10). Ligado, e-mail com `X-MS-Exchange-Organization-SCL` ≥ `limite_scl` (5) → **Ignorados** com motivo `SPAM`. Desligado por padrão |

Além do assunto, a detecção de resposta automática usa a classe da mensagem (`REPORT.*`, modelo de ausência) e os cabeçalhos `Auto-Submitted`, `X-Autoreply` e `Precedence`. Isso fica no código porque é padrão de protocolo, não regra de negócio.

### `classificacao`

| Chave | Descrição |
|---|---|
| `tipo` | `palavras_chave` (implementado), `ia` (F08) ou `menu` (F09) |
| `limite_confianca` | Abaixo dele a categoria vira `MANUAL – BAIXA CONFIANÇA`. Valor inicial **0,70**, conservador, porque a especificação diz que o erro grave é o que mais pesa |
| `arquivo_termos` | `config/palavras_chave.yaml` |

### `classificacao.ia` (v0.2.0)

Usado só com `classificacao.tipo: ia`. Referência: especificação funcional de 22/10/2026 (seções 3, 5, 6 e 7).

| Chave | Padrão | Descrição |
|---|---|---|
| `limite_confianca` | `0.80` | Com `tipo: ia`, **substitui** `classificacao.limite_confianca` (regra D3, seção 6.2). Voltar para `palavras_chave` restaura o 0,70 (RNF-IA08) |
| `arquivo_categorias` | `config/categorias_ia.yaml` | Categorias C → tutorial e habilitação (seção 6.4) |
| `arquivo_prompt` | `config/prompts/classificacao_v1.txt` | Prompt do Anexo A. A versão é o nome do arquivo e o hash (SHA-256, 12 caracteres) vai para o registro. **Nunca sobrescreva:** crie `classificacao_v2.txt` (RNF-IA02) |
| `timeout_segundos` | `30` | Tempo máximo de cada chamada |
| `novas_tentativas` / `esperas_segundos` | `2` / `[2, 4]` | Novas tentativas após timeout/erro HTTP e a espera antes de cada uma |
| `correcoes_formato` | `1` | Nova chamada com `mensagem_correcao` quando o JSON vem inválido (máximo 1 – E4) |
| `max_falhas_seguidas` | `5` | Depois disso a IA é desligada até o fim do ciclo e os analistas recebem um aviso único (RNF-IA03) |
| `limite_corpo` / `limite_historico` | `6000` / `2000` | Caracteres enviados à IA (RN3.2) |
| `texto_vazio` | `(nenhum)` | Texto usado no prompt quando não há anexos ou histórico |
| `mensagem_correcao` | "Responda somente com o JSON válido no formato especificado" | Texto da chamada de correção (E4) |
| `resumo_padrao` | "Resumo indisponível – ver e-mail original" | Resumo usado quando a IA falha ou não devolve resumo num caso manual |
| `assunto_alerta` | "[RPA Dúvidas Financeiras] Classificação por IA indisponível" | Assunto do aviso de falhas seguidas (modelo `aviso_ia_indisponivel.html.j2`) |
| `provedor.tipo` | `simulado` | `simulado` (sem rede, regras de `ia_simulada.yaml`) ou `http_generico` (provedor corporativo – PA08) |
| `provedor.simulado.arquivo_regras` | `config/ia_simulada.yaml` | Regras do provedor simulado |

#### `classificacao.ia.provedor.http_generico`

Tudo o que é específico do provedor fica aqui, nada no código. Os valores abaixo seguem o formato de *chat completions* mais comum; ajuste ao contrato do provedor aprovado.

| Chave | Exemplo | Descrição |
|---|---|---|
| `endpoint` | `""` | URL completa do serviço. **Obrigatória** com este provedor |
| `modelo` | `""` | Identificador do modelo |
| `credencial` | `ia_api_key` | Nome passado a `segredos.obter()`: variável `RPA_IA_API_KEY` ou Gerenciador de Credenciais |
| `cabecalhos` | `{Authorization: "Bearer {credencial}"}` | `{credencial}` é trocado pelo segredo no momento da chamada |
| `temperatura` / `campo_temperatura` | `0` / `temperature` | RN3.3 |
| `modo_json` / `parametros_modo_json` | `true` / `{response_format: {type: json_object}}` | Parâmetros acrescentados ao corpo quando o provedor oferece modo JSON |
| `campo_modelo` / `campo_mensagens` | `model` / `messages` | Nomes dos campos da requisição |
| `corpo_extra` | `{}` | Outros parâmetros fixos da requisição |
| `caminho_texto_resposta` | `choices.0.message.content` | Onde está o texto gerado na resposta (números indexam listas) |
| `caminho_tokens` / `caminho_modelo` | `usage.total_tokens` / `model` | Tokens e modelo efetivamente usados (vão para o registro) |

Falhas do provedor: timeout e erro HTTP/conexão → novas tentativas; credencial ausente → sem nova tentativa. Em todos os casos o e-mail vai para manual com `IA_INDISPONIVEL`. Só o código do erro vai para o log (o corpo do erro pode ecoar o prompt).

### `respostas`

| Chave | Descrição |
|---|---|
| `pasta_modelos` | `config/modelos` |
| `link_forms_po` | Link do Forms de solicitação de PO (RF07) |
| `assinatura` | Assinatura das respostas |
| `faixa_ambiente` | Faixa amarela no topo de cada mensagem gerada (dev/demo), para nenhum rascunho de teste ser confundido com resposta oficial |
| `prefixo_manual` | `[MANUAL – {motivo}]` |
| `rotulos_motivo_manual` | Texto de cada motivo no assunto. v0.2.0: `MULTIPLAS_DUVIDAS`, `EXCECAO`, `SEM_RESPOSTA_PADRAO`, `CATEGORIA_DESABILITADA`, `CATEGORIA_SEM_TUTORIAL`, `IA_INDISPONIVEL`, `RESPOSTA_IA_INVALIDA` |
| `responder_todos` | `false` = responde ao remetente + analistas em CC |

### `tutoriais`, `registro`, `extracao`

| Chave | Descrição |
|---|---|
| `tutoriais.arquivo` | `tutoriais.yaml` (SharePoint) ou `tutoriais_demo.yaml` (fictícios) |
| `registro.pasta_logs` / `nivel_log` | Log técnico diário |
| `registro.banco_estado` | SQLite de estado (um por perfil) |
| `registro.planilha_controle` | Planilha `.xlsx` |
| `extracao.marcadores_historico` | Regex que marcam o início do histórico citado |
| `extracao.marcadores_assinatura` | Regex de fechamento/assinatura (linha inteira) |
| `extracao.marcadores_aviso_legal` | Regex de avisos de confidencialidade |
| `extracao.limite_historico` (v0.2.0) | Tamanho máximo do `historico_resumido` (2.000), o trecho do histórico citado que vai como contexto para a IA (E1) |

## 3. Arquivos auxiliares

### `tutoriais.yaml`

```yaml
raiz: "${USERPROFILE}/<Empresa>/<Site> - Documentos/Tutoriais"   # pasta do SharePoint sincronizada
limite_anexo_mb: 20
categorias:
  TUT_CONNECT: { pasta: "04. Suporte Connect", padrao: "*.pptx", descricao: "Acesso ao Connect" }
```

As regras da seção 6 da especificação estão implementadas: busca por glob, o arquivo mais recente vence, ele precisa existir com tamanho > 0 e dentro do limite. Arquivos `~$*` (temporários do Office) são ignorados. No Windows, um arquivo que **só existe na nuvem** (OneDrive) é recusado, com a orientação de marcar "Sempre manter neste dispositivo". Para desligar essa checagem, use `exigir_arquivo_local: false`.

### `palavras_chave.yaml`

Termos e pesos por categoria, mais duas categorias especiais que sempre viram encaminhamento: `MANUAL_SAP` e `MANUAL_FORA_ESCOPO`. A fórmula da confiança está explicada no próprio arquivo. Para calibrar, veja o doc 05.

### `categorias_ia.yaml` (v0.2.0)

```yaml
codigos_validos: [C03, C05, C06, C07, C99]      # lista fechada do contrato (V3/V4)
sinais_excecao: [ERRO_SISTEMA, ..., MENSAGEM_INTERNA]   # lista fechada (V8)
categorias:
  C03: { descricao: "Envio / upload de NF", tutorial: TUT_UPLOAD_NF, resposta_automatica: true }
  C05: { descricao: "Cadastro de fornecedor", tutorial: TUT_CADASTRO, resposta_automatica: true }
  C06: { descricao: "Reembolso", tutorial: TUT_REEMBOLSO, resposta_automatica: false }   # até PA03
  C07: { descricao: "Formulários (Forms)", tutorial: null, resposta_automatica: false, motivo_manual: SEM_RESPOSTA_PADRAO }
  C99: { descricao: "Não mapeada", tutorial: null, resposta_automatica: false, motivo_manual: NAO_IDENTIFICADO }
```

- **Habilitar o reembolso** (depois da decisão PA03): `C06.resposta_automatica: true`. Nenhuma linha de código muda.
- `tutorial` precisa ser uma categoria de tutorial do robô (`TUT_*`) com entrada no arquivo de tutoriais e modelo `.html.j2`; o `verificar` confere.
- Código válido sem entrada em `categorias` → manual `CATEGORIA_SEM_TUTORIAL` (o `verificar` alerta).
- Mudar `codigos_validos` ou `sinais_excecao` exige uma nova versão do prompt.

### `prompts/classificacao_v1.txt` (v0.2.0)

Texto **idêntico** ao Anexo A da especificação (um teste confere o hash). O robô troca `{{ASSUNTO}}`, `{{CORPO}}`, `{{ANEXOS}}` e `{{HISTORICO}}` pelo conteúdo **mascarado e truncado**, numa única passada; `<<<`/`>>>` dentro do e-mail são neutralizados para o texto não fechar os delimitadores (RNF-IA05).

### `ia_simulada.yaml` (v0.2.0)

Regras do provedor **simulado** (não é IA): a primeira regra cujo termo aparece no assunto/corpo define o JSON devolvido; `falha: timeout | erro | json_invalido | json_invalido_uma_vez` simula falhas da IA. Os marcadores `[[simular_timeout]]`, `[[simular_json_invalido]]` e `[[simular_json_corrigido]]` no corpo de um e-mail de demonstração acionam essas falhas.

### `fornecedores*.yaml`

```yaml
emails:   ["financeiro@fornecedor.com.br"]
dominios: ["fornecedor.com.br"]
```

### `modelos/*.html.j2`

Um arquivo por categoria (`TUT_CONNECT.html.j2` etc.), mais `_base.html.j2` (saudação, fechamento e assinatura), `encaminhamento_manual.html.j2` (nota interna) e `aviso_erro.html.j2`. Os **textos atuais são provisórios** e aguardam a aprovação da área (S09).

| Variável disponível | Conteúdo |
|---|---|
| `nome_arquivo`, `descricao_tutorial` | Tutorial anexado |
| `link_forms` | `respostas.link_forms_po` |
| `assinatura`, `faixa_ambiente` | Da configuração |
| `protocolo` | Código curto e estável do e-mail (8 caracteres), igual ao do registro |
| `data`, `assunto`, `nome_remetente` | Do e-mail |

Na nota de encaminhamento (`encaminhamento_manual.html.j2`), desde a v0.2.0, também: `resumo_duvida`, `categoria_docx`, `duvidas_secundarias` e `sinais_excecao` (sempre presentes, vazios quando o classificador não os produz – o Jinja usa `StrictUndefined`). O aviso `aviso_ia_indisponivel.html.j2` recebe `falhas`.

## 4. Credenciais

O MVP com Outlook COM **não usa credencial**: aproveita o login que o Outlook já resolveu. Para o Graph e a IA, `segredos.obter("nome")` procura primeiro a variável `RPA_<NOME>` e depois o Gerenciador de Credenciais do Windows:

```bat
python -m keyring set rpa_duvidas graph_client_secret
python -m keyring set rpa_duvidas ia_api_key        :: credencial da IA (provedor http_generico)
```

Nunca coloque segredos nos YAML nem no repositório.
