# Histórico de versões

## 0.3.3 – 12/11/2026

Correções do 2º teste da operação assistida (12/11/2026, 60 e-mails, nenhum respondido). **A planilha `configuracao.xlsx` não muda**: o modelo continua 0.3.0 e a planilha já configurada na máquina do analista serve como está.

**Corrigido**

- **Corpo do e-mail descartado.** O aviso de "e-mail externo" que o servidor põe no topo (aviso + endereço do remetente + linha horizontal) fazia a linha horizontal ser lida como início do histórico: a classificação usava só o assunto e a confiança não passava de 0,40. Agora `extracao.remover_preambulo()` tira esse bloco do começo do texto antes de procurar o histórico. Os avisos reconhecidos ficam na chave nova `extracao.banners_ignorados` do `settings.yaml` (empacotado no executável).
- **Arquivamento `.msg` com pasta comprida.** Com a pasta de arquivamento dentro do OneDrive (182 caracteres), 48 dos 60 e-mails não foram arquivados. Quando o caminho não cabe em 240 caracteres mesmo sem o assunto, o nome da pasta do escritório é encurtado para o espaço que sobra (mínimo de 8 caracteres). O corte depende só da pasta raiz, então o mesmo escritório cai sempre na mesma pasta. Os que falharam podem ser refeitos com `arquivar-pendentes`.

**Alterado**

- **Avisos da planilha de escritórios.** No log do ciclo sai uma linha de resumo (INFO); a lista por linha continua no "Verificar configuração" e, no log, só com `nivel_log` DEBUG. A leitura da planilha não mudou: é só conferência de formato, sem consulta externa.
- Versão interna 0.3.3. Testes: `tests/test_v033_segundo_teste.py` (dados fictícios).

**Pendente (depende da planilha de configuração, congelada até o fim da operação assistida)**

- Calibração dos termos e pesos da aba Palavras_chave com os e-mails reais.

## 0.3.2 – 12/11/2026

Decisões da área sobre o 1º teste (detalhes em `docs/14_ajustes_v0.3.1.md`).

**Incluído**

- Download automático de arquivos do OneDrive "somente on-line" (`nuvem.py`): planilha de escritórios e tutoriais são baixados antes de usar, com tempo limite por arquivo. Antes de ler os e-mails, o ciclo prepara todos os tutoriais e registra o resultado no log. Chaves novas `onedrive.baixar_automaticamente` e `onedrive.tempo_limite_s`.
- Testes `tests/test_v032_onedrive_e_decisoes.py`, incluindo as decisões 1 (e-mail exato e domínio) e 5 ("CNPJ não consta" continua fornecedor).

**Alterado**

- Versão interna 0.3.2.

## 0.3.1 – 12/11/2026

Correção do 1º teste da operação assistida: o ciclo não rodava porque a planilha de escritórios tinha o mesmo domínio com nomes de escritório diferentes. Detalhes em `docs/14_ajustes_v0.3.1.md`.

**Alterado**

- Planilha de escritórios lida por **e-mail** (prioridade) e por domínio. Conflitos, `#N/A`, "CNPJ não consta…", repetições e células que não são e-mail viram avisos com o número da linha no log e no `verificar`; o ciclo só deixa de rodar se a planilha estiver inacessível ou sem nenhuma linha válida.
- E-mail de domínio público (gmail etc.) na planilha reconhece só aquele endereço, não o domínio inteiro.
- `DOMINIO_INTERNO` aceita e-mail completo (vale como caixa).
- `verificar` avisa quando `caminho_arquivo_emails` não é um caminho completo.
- Nova chave `escritorios.valores_sem_escritorio` (padrão: "CNPJ não consta na base de fornecedores").
- Versão interna 0.3.1. Testes: `tests/test_v031_planilha_escritorios.py` (dados fictícios com os padrões da planilha real).

## 0.3.0 – 05/11/2026

Executável configurável por planilha, para a calibração na máquina do analista, conforme a `Especificacao_Tecnica_v0.3.0_EXE_Calibracao.md` (v1.0, 05/11/2026). Detalhes, decisões da análise e desvios em `docs/13_ajustes_v0.3.0.md`; guia de instalação (rascunho) em `docs/12_guia_instalacao_v0.3.0.md`. Sem o perfil `calibracao`, o comportamento é o da v0.2.1: as chaves novas têm padrão que a reproduz.

**Incluído**

- Perfil **`calibracao`** (D01–D04): caixa pessoal, sem mover, respostas só para o e-mail destino padrão (`destino_respostas: TESTE`), IA desligada, caso manual categorizado (`acao_manual: CATEGORIZAR`).
- **`config\configuracao.xlsx`** (seção 5): abas LEIA-ME, Geral, Categorias, Palavras_chave, Textos, Tutoriais, Destinatarios, Filtros e Listas. `scripts/gerar_modelo_config.py` gera o modelo (com `A_PREENCHER`) ou migra um perfil YAML. `config_xlsx.ler_configuracao_xlsx()` copia o arquivo antes de abrir e devolve `ErroCelula` com aba, linha e coluna; qualquer erro impede a execução. Mescla `settings.yaml` → perfil → xlsx.
- **Raízes do executável** (seção 4.4): `raiz_aplicacao()` (pasta do .exe: planilha, `modelos\`, `dados\`, `logs\`, `arquivo\`) e `raiz_recursos()` (arquivos empacotados). Um `.j2` em `modelos\` substitui o padrão.
- **Planilha de escritórios** (D06): mapa domínio → escritório, lido a cada ciclo e usado como lista de fornecedores e para o escritório do e-mail. Planilha indisponível: o ciclo não roda e o aviso sai uma vez por dia.
- **Caixa pessoal** (seção 6.1): `marcar_nao_fornecedores` (não fornecedores não são alterados nem registrados; o filtro roda antes do lote; contador `nao_fornecedores`) e `pular_ja_respondidos` (`PR_LAST_VERB_EXECUTED` 102/103/104 → Ignorados com `JA_TRATADO_PELO_ANALISTA`, só a categoria).
- **Envio de teste** (D02, seção 6.2):
  - `responder(redirecionar_para=…)` mantém o fio do `Reply()`, remove todos os destinatários e zera o CC;
  - **trava por operação** (`TravaDestinatarios`) que relê `Recipients` em SMTP antes do `Send`/`Save` e bloqueia quando o SMTP não é identificado;
  - coluna `destinatario_original` e faixa da calibração.
- **Envio por categoria** (D10, seção 6.7): envia só com modo REAL, categoria liberada e categoria não bloqueada; status por e-mail (CONCLUIDO ou SIMULADO). Categoria desativada vai para manual. Bloqueio automático por "Tutorial errado" depois da data de liberação, com aviso único a AVISO_ERRO.
- **Tutoriais pelo caminho completo e link do Forms** (D07); FORMS_PO sem link vai para manual.
- **Aba Textos** (D09): `RESP_<CATEGORIA>`, `AVISO_AUTOMATICO` (em toda resposta), `ASSINATURA` e `NOTA_MANUAL`; texto escapado, um `<p>` por linha; ação `RESPONDER_TEXTO`; prefixo no assunto.
- **Arquivamento .msg** (D05): `<raiz>\<Escritório>\<AAAA-MM>\…_<protocolo>_<assunto>.msg`. Uma falha não desfaz a resposta e grava `FALHA: …`. Comando `arquivar-pendentes`.
- **Retorno manual** (D08): tabela `retorno_manual` (fonte da verdade), lida da planilha a cada exportação sem que uma célula vazia apague o valor gravado. A aba Registro fica protegida, com só o retorno editável e validações. O Resumo mostra, por categoria, avaliados, acerto, erros graves e tempo economizado. Colunas novas: escritório, destinatário original, destino das respostas, enviado, categoria liberada, arquivado em, máquina, usuário e versão.
- **`verificar` ampliado** (seção 7.2), salvo em `logs\verificar_*.txt`, e **menu do console** (duplo clique no .exe).
- **Build** (seção 7.1): `rpa_duvidas.spec` (onedir, importações ocultas), `build_exe.bat` (testes, build, modelo da planilha, `versao.txt`, zip), `scripts/rpa_exe.py`, `scripts/gravar_versao.py`, `requirements-build.txt`.
- 163 testes novos (`tests/test_v030_*.py`, `tests/fakes_outlook.py`), com testes dedicados aos critérios de aceite 2, 3 (64 combinações, incluindo um destinatário que `Recipients.Remove` não tira) e 9. Total: 402, todos passando.

**Alterado**

- Versão interna 0.3.0 (`__init__.py`, `pyproject.toml`).
- `.gitignore`: `dados/` passou a valer só na raiz (`/dados/`), para não esconder a massa de teste `tests/dados/massa_emails_sintetica.csv`, que agora é versionada. Novos itens: `dist/`, `build/`, `/arquivo/`, `logs/*.txt` e `/config/configuracao.xlsx`.
- `_base.html.j2`: aviso de resposta automática e assinatura podem vir da aba Textos; sem eles, o texto é o da v0.2.1.
- `rpa_duvidas.ciclo.ErroSeguranca` agora é a mesma classe de `rpa_duvidas.caixa.base.ErroSeguranca`.

**Pendente:** build e teste do .exe em uma máquina sem Python (T15), revisão do guia pelo financeiro e o PDF (T16), instalação assistida (T17) e os pontos em aberto da seção 12 – ver docs/13.

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
