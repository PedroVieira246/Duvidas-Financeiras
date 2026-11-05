# Histórico de versões

## 0.2.1 – 27/10/2026

Ajustes do primeiro teste real na máquina do Pedro (Outlook LTSC 2021, conta Microsoft 365 configurada como **Exchange ActiveSync**). Detalhes em `docs/11_ajustes_v0.2.1.md`. Sem as chaves novas, o comportamento é o da v0.2.0.

**Incluído**

- Modo **sem mover** (`caixa.mover_apos_tratar: false`): marca como lido, aplica a categoria `RPA - …` e não chama `Move`. Itens com categoria do RPA são pulados na leitura e, na reconciliação, recebem a categoria correspondente.
- Filtros de leitura `caixa.filtro_assunto`, `caixa.recebidos_desde` e `caixa.max_varredura`. Com eles (ou no modo sem mover), a leitura examina os itens mais recentes, ignora convites de reunião e e-mails já tratados e entrega o lote em ordem de chegada.
- Proteção contra laço `filtros.mensagens_do_rpa` → Ignorados com o novo motivo `PROPRIO_RPA`. Funções `extracao.ultima_mensagem()` e `extracao.detectar_mensagem_do_rpa()`; campos `EmailRecebido.gerada_pelo_rpa` / `motivo_gerada_pelo_rpa`. A `previa` mostra o caso.
- `verificar`: linha INFO com a pasta e o modo de leitura, aviso de conta ActiveSync e erro se a conta for ActiveSync com `mover_apos_tratar: true`. Novo método `CaixaEmail.avisos()`.
- Tutorial fictício `Upload de NF/PYM (Connect) - Upload e consulta de NFs.pdf` e gerador de PDF sem dependências em `scripts/preparar_demo.py`.
- 20 testes novos (`tests/test_v021_caixa_entrada.py`). Total: 239, todos passando.

**Alterado**

- Perfil `dev`: lê `@inbox` com `filtro_assunto: "[RPA-TESTE]"`, `recebidos_desde: "2026-10-27"` e `mover_apos_tratar: false`.
- `TUT_UPLOAD_NF` em `tutoriais.yaml` e `tutoriais_demo.yaml`: padrão `*Upload e consulta de NFs*.pdf` (formato usado pela área no histórico; confirmar no S05).
- Aviso de erro diz "continua na pasta de entrada, com a categoria RPA - Erro" quando o e-mail não é movido.
- Destinatários da resposta sem duplicidade no registro (remetente = analista em CC no teste).
- `scripts/enviar_emails_teste_outlook.py`: não move quando a pasta de entrada é a Caixa de Entrada e não quebra se o Move falhar.
- Teste de pendências `<PREENCHER>` passou a usar o perfil `prod` (o `dev` já está preenchido).

## 0.2.0 – 23/10/2026

Classificação por **IA generativa (F08)**, conforme a `especificacao_funcional_classificacao.md` (v1.0, 22/10/2026). O padrão continua `classificacao.tipo: palavras_chave`: **sem ligar a IA, o robô se comporta exatamente como a v0.1.0** (os 81 testes antigos passam sem ajuste).

**Incluído**

- `classificacao/ia.py` → `ClassificadorIA` (interface `Classificador`): mascaramento, prompt do Anexo A, chamada com timeout de 30 s e 2 novas tentativas (espera de 2 s e 4 s), no máximo 1 chamada de correção de formato, validação, decisão e `Classificacao` com detalhes (JSON da IA, categoria do .docx, resumo, secundárias, sinais, modelo, versão/hash do prompt, latência, tentativas, tokens). Falha da IA = MANUAL `IA_INDISPONIVEL`, nunca exceção para o ciclo (R3). Depois de 5 falhas seguidas no ciclo, a IA é desligada até o fim do ciclo e os analistas recebem um aviso único (RNF-IA03).
- `classificacao/validacao_ia.py` (E4, V1–V10) e `classificacao/decisao_ia.py` (E5, D1–D7 nesta ordem), só com funções puras.
- `classificacao/provedores_ia.py` → interface `ProvedorIA` com dois provedores: `simulado` (roteiro ou regras de `config/ia_simulada.yaml`, sem rede) e `http_generico` (endpoint, modelo, cabeçalhos, campos e caminhos da resposta no `settings.yaml`; credencial via `segredos.obter()`; temperatura 0; modo JSON opcional). Nenhum endpoint, chave ou nome de provedor no código (PA08 em aberto).
- `mascaramento.py` (RN3.1/RN3.2): CNPJ, CPF, agência/conta/banco, chave PIX e telefone; truncamento do corpo (6.000) e do histórico (2.000) com `[...]`.
- `config/prompts/classificacao_v1.txt` (Anexo A, idêntico à especificação) e `config/categorias_ia.yaml` (seção 6.4: C03/C05 habilitadas, C06 desabilitada, C07/C99 sem tutorial).
- Interface `Classificador.classificar(assunto, corpo, email=None)` (R1); o ciclo passa o `EmailRecebido`.
- `EmailRecebido.historico_resumido` e `extracao.extrair_historico()` (E1, até 2.000 caracteres).
- Filtros E2: e-mail interno (`filtros.dominios_internos` + a própria caixa) e spam opcional (cabeçalho SCL ≥ 5) → Ignorados com motivo `INTERNO` / `SPAM`, sem chamar a IA. Vazios/desligados por padrão.
- Novos motivos de manual: `MULTIPLAS_DUVIDAS`, `EXCECAO`, `SEM_RESPOSTA_PADRAO`, `CATEGORIA_DESABILITADA`, `CATEGORIA_SEM_TUTORIAL`, `IA_INDISPONIVEL`, `RESPOSTA_IA_INVALIDA` (rótulos em `respostas.rotulos_motivo_manual`).
- Encaminhamento (E7): nota com resumo da IA, categoria do .docx, dúvidas secundárias e sinais de exceção (`encaminhamento_manual.html.j2` + `nota_manual()`, R6). Novo modelo `aviso_ia_indisponivel.html.j2`.
- Registro (E8): 12 colunas novas em `eventos` e na planilha, tabela separada `respostas_ia` (JSON bruto) e migração automática (`ALTER TABLE`) de banco existente (R7). Log técnico da IA sem corpo, prompt nem resumo (RN8.2).
- Configuração: `classificacao.ia.*` (limite 0,80 quando `tipo: ia`), `filtros.dominios_internos`, `filtros.spam`, `extracao.limite_historico`; novo perfil `demo_ia` (caixa simulada + IA simulada). `envio_real: false` em todos os perfis.
- Comando `verificar`: prompt, `categorias_ia.yaml`, mapeamento categoria → tutorial/modelo, provedor e credencial da IA; alerta de lista de fornecedores vazia em prod.
- `scripts/avaliar_classificador.py`: `--classificador ia|palavras_chave` e `--limites 0.70,0.75,...` com tabela de calibração (acerto, % manual e erros graves por limite – seção 6.2).
- `scripts/preparar_demo.py --ia`: cenários da IA para o perfil `demo_ia`.
- 138 testes novos (total 219).

**Não muda:** E6 (resposta com tutorial), idempotência, trava de destinatários, modo simulação. O texto gerado pela IA nunca vai ao fornecedor: a resposta continua vindo dos modelos `TUT_*.html.j2`.

**Pendente:** provedor corporativo de IA (PA08), calibração com a massa real (PA15) e demais pontos em aberto – ver docs/10.

## 0.1.0 – 19/10/2026

Primeira versão da Frente 1, seguindo a sequência recomendada do plano de ação (F01+F02 → F03+F04 → F12 → F06 → F15+F16).

**Incluído**

- Configuração em camadas (base + perfis `dev`, `demo`, `prod`), com validação, detecção de valores `<PREENCHER>` e trava de destinatários fora de produção.
- Interfaces `CaixaEmail` e `Classificador`, com as fábricas correspondentes.
- Adaptador Outlook clássico via pywin32 (pastas por `@inbox`, remetente Exchange→SMTP, rascunho ou envio, CC, anexo, categoria, mover).
- Caixa simulada em disco para demonstração e testes, com visualização HTML das mensagens geradas.
- Extração: HTML→texto, remoção de histórico, assinatura e aviso legal, detecção de respostas automáticas.
- Classificador por palavras-chave com pesos, peso do assunto, confiança (dominância × força) e categorias especiais SAP / fora do escopo.
- Tutoriais: glob, mais recente, validação de tamanho e de arquivo só na nuvem.
- Modelos de resposta Jinja2 (provisórios) para as 5 categorias respondíveis, a nota de encaminhamento e o aviso de erro.
- Ciclo com idempotência (estado antes e depois da ação), reconciliação, tratamento de erro sem interromper o ciclo e aviso aos analistas.
- Registro: log diário, SQLite e planilha de controle (Registro / Ciclos / Resumo).
- Comandos `executar` (`--loop`), `previa`, `verificar`, `reprocessar` e `exportar`.
- Scripts: preparar a demonstração, gerar e-mails de teste no Outlook e avaliar o classificador.
- Testes automatizados e massa sintética de 40 e-mails.
- Documentação completa em `docs/`.

**Pendente:** ver docs/01 (status) e docs/08 (solicitações).
