# 11 · Ajustes da v0.2.1 – Caixa de Entrada e conta ActiveSync

**Data:** 27/10/2026 · **Base:** v0.2.0 · **Backup da versão anterior:** `..\rpa_duvidas_financeiras_v0.2.0_backup_antes_v0.2.1.zip`

> A pasta continua com o nome `rpa_duvidas_financeiras_v0.2.0` para não quebrar o `.venv` nem os caminhos já configurados. A versão interna passou a 0.2.1 (`__init__.py`, `pyproject.toml`).

## 1. Contexto

No primeiro teste real (Outlook LTSC 2021, conta Microsoft 365):

1. A conta está no Outlook como **Exchange ActiveSync**. O Outlook recusa o `Move` via COM ("Infelizmente, o Exchange ActiveSync não oferece suporte…"). A resposta saía, mas o e-mail não ia para a pasta de destino e caía em Erro.
2. Os e-mails que deram erro depois de respondidos voltavam a cada ciclo e geravam **um aviso de erro novo por ciclo**.
3. O tutorial de Upload de NF é enviado pela área em **PDF**, mas a configuração só procurava `.pptx`.
4. O pedido agora é ler e responder **direto na Caixa de Entrada principal**. Isso cria dois riscos: tratar e-mails pessoais e o robô responder às próprias respostas (laço).

## 2. Alterações no código

| Arquivo | O que mudou | Por quê |
|---|---|---|
| `src/rpa_duvidas/caixa/outlook_com.py` | Parâmetros novos: `mover_apos_tratar`, `filtro_assunto`, `recebidos_desde`, `max_varredura`, `categorias_rpa`. Com `mover_apos_tratar=False`, o `finalizar()` marca como lido, aplica a categoria, salva e **não** chama `Move`. Nova leitura filtrada (`_selecionar_filtrado`): examina os itens mais recentes, para na data mínima, aplica o filtro de assunto, ignora convites de reunião e itens que já têm categoria do RPA, e devolve o lote do mais antigo para o mais novo. Sem as opções novas, a leitura é a mesma da v0.2.0. | ActiveSync e leitura segura da Caixa de Entrada pessoal |
| `src/rpa_duvidas/caixa/outlook_com.py` | `tipo_conta()` identifica o tipo da conta dona da pasta (`OlAccountType`). `avisos()` informa o modo de leitura e avisa quando a conta é ActiveSync. `verificar()` acusa erro quando a conta é ActiveSync com `mover_apos_tratar: true` e deixa de exigir as pastas de destino no modo sem mover. | Diagnóstico claro no `verificar` |
| `src/rpa_duvidas/caixa/outlook_com.py` | Função `_data_local()` para as datas do COM (reaproveitada no `_converter`). | Comparar datas com fuso do pywin32 |
| `src/rpa_duvidas/caixa/base.py` | Método `avisos()` na interface, com retorno vazio por padrão. | Caixas simulada e Graph seguem funcionando |
| `src/rpa_duvidas/caixa/__init__.py` | A fábrica lê as chaves novas e interpreta `recebidos_desde` (`AAAA-MM-DD` ou data do YAML; formato inválido gera erro de configuração). | Configuração |
| `src/rpa_duvidas/extracao.py` | `ultima_mensagem()` devolve o texto até o histórico, sem cortar o rodapé. `detectar_mensagem_do_rpa()` reconhece mensagens do próprio robô pelo assunto (`[MANUAL – …]`, `[RPA Dúvidas Financeiras]`) ou pelo rodapé "Resposta automática · protocolo XXXXXXXX" na **última** mensagem. `processar()` ganhou o parâmetro opcional `marcas_rpa`. | Proteção contra laço sem ignorar fornecedores que citam o robô no histórico |
| `src/rpa_duvidas/modelos.py` | `MotivoIgnorado.PROPRIO_RPA`; campos `EmailRecebido.gerada_pelo_rpa` e `motivo_gerada_pelo_rpa`. | Proteção contra laço |
| `src/rpa_duvidas/ciclo.py` | Passo 1a: mensagem do próprio RPA vai para Ignorados com motivo `PROPRIO_RPA`. A reconciliação, no modo sem mover, aplica a categoria correspondente (respondido, encaminhado, ignorado, erro ou simulado) em vez de mover. No erro, o destino só fica registrado quando o e-mail é movido. O aviso de erro informa se o e-mail foi movido. Destinatários sem duplicidade. | Evita laço e avisos repetidos |
| `src/rpa_duvidas/respostas.py` + `config/modelos/aviso_erro.html.j2` | Parâmetro `movido`: "foi movido para a pasta Erro" ou "continua na pasta de entrada, com a categoria RPA - Erro". | Texto correto no modo sem mover |
| `src/rpa_duvidas/__main__.py` | O `verificar` mostra as linhas `INFO` da caixa. A `previa` passa as marcas do RPA e mostra "IGNORAR – PRÓPRIO RPA". | Diagnóstico |
| `scripts/enviar_emails_teste_outlook.py` | Não move quando a pasta de entrada é a Caixa de Entrada. Se o `Move` falhar, avisa em vez de quebrar. | Uso com `@inbox` e ActiveSync |
| `scripts/preparar_demo.py` | O tutorial de NF passou a ser `.pdf`. Novo `pdf_ficticio()` gera um PDF de uma página sem bibliotecas extras. | Tutoriais fictícios |
| `src/rpa_duvidas/__init__.py`, `pyproject.toml` | Versão 0.2.1. | — |

## 3. Alterações na configuração

| Arquivo | Chave | Antes | Depois |
|---|---|---|---|
| `config/settings.yaml` | `caixa.mover_apos_tratar` | — | `true` (padrão: comportamento da v0.2.0) |
| `config/settings.yaml` | `caixa.filtro_assunto` / `recebidos_desde` / `max_varredura` | — | `""` / `""` / `500` |
| `config/settings.yaml` | `filtros.mensagens_do_rpa` | — | ligado, com 2 padrões de assunto e 2 de texto |
| `config/perfis/dev.yaml` | `caixa.pasta_entrada` | `@inbox/RPA_Teste` | `@inbox` |
| `config/perfis/dev.yaml` | `caixa.filtro_assunto` | — | `"[RPA-TESTE]"` (**não deixar vazio na caixa pessoal**) |
| `config/perfis/dev.yaml` | `caixa.recebidos_desde` | — | `"2026-10-27"` |
| `config/perfis/dev.yaml` | `caixa.max_varredura` | — | `300` |
| `config/perfis/dev.yaml` | `caixa.mover_apos_tratar` | — | `false` |
| `config/tutoriais_demo.yaml` e `config/tutoriais.yaml` | `TUT_UPLOAD_NF.padrao` | `*Upload e consulta de NFs*.pptx` | `*Upload e consulta de NFs*.pdf` |

Os valores que você já tinha preenchido no `dev.yaml` (domínio, e-mails, `envio_real: false`) foram mantidos. O `prod.yaml` não mudou: ele continua movendo, e a conta da automação precisa estar como Microsoft Exchange (S03/S04).

## 4. Arquivos novos

| Arquivo | Conteúdo |
|---|---|
| `dados_teste/tutoriais/Upload de NF/PYM (Connect) - Upload e consulta de NFs.pdf` | Tutorial **fictício** em PDF (o `.pptx` antigo continua na pasta, mas não é mais usado) |
| `tests/test_v021_caixa_entrada.py` | 20 testes: modo sem mover, filtros de leitura, ordem e limite, convites, ActiveSync no `verificar`, datas, proteção contra laço (resposta, encaminhamento, aviso e fornecedor citando o robô), aviso de erro, ciclo completo na Caixa de Entrada e erro sem aviso repetido |
| `docs/11_ajustes_v0.2.1.md` | Este documento |

Testes ajustados: `test_outlook_com.py` (o `Sort` falso respeita a ordem decrescente), `test_config.py` (as pendências de `<PREENCHER>` agora são verificadas no `prod`) e `test_ciclo_ia.py` (tutorial de NF em PDF). Resultado: **239 testes passando**.

Documentação atualizada: `CHANGELOG.md`, `docs/03_configuracao.md` (chaves novas) e `docs/04_guia_execucao_windows.md` (seção 4.5 e erro do ActiveSync).

## 5. Como o dev funciona agora

1. O robô lê a Caixa de Entrada, mas só os e-mails com `[RPA-TESTE]` no assunto recebidos desde 27/10/2026 (até 300 mais recentes examinados).
2. Para cada e-mail: classifica, responde ou encaminha (em rascunho, porque `envio_real: false`), marca como lido e aplica a categoria `RPA - Simulado`. O e-mail **fica** na Caixa de Entrada.
3. No ciclo seguinte, e-mails com categoria `RPA - …` são pulados.
4. Respostas, encaminhamentos e avisos do próprio robô que chegam à Caixa de Entrada vão para Ignorados (`PROPRIO_RPA`), com a categoria `RPA - Ignorado`.
5. Para repetir um teste: `.\rpa.bat reprocessar <PROTOCOLO> --perfil dev` e remova a categoria do e-mail no Outlook.

## 6. Pontos de atenção

- **Categorias no ActiveSync:** o teste de 27/10 indica que salvar a categoria funciona (a falha ocorreu só no `Move`). Se a categoria não for gravada, o e-mail volta na leitura seguinte e é só reconciliado: não é respondido de novo, porque o registro SQLite impede, mas aparece no log. Confira no primeiro ciclo.
- **Os 6 e-mails do teste de 16:53** estão na pasta `RPA_Teste`, que não é mais lida, então não geram novos avisos. As respostas que o robô enviou de verdade às 16:53 (`RE: [RPA-TESTE] …`) estão na Caixa de Entrada e serão ignoradas como `PROPRIO_RPA` no próximo ciclo, ficando marcadas como lidas.
- **Produção:** o modo sem mover é uma solução para o teste. Na caixa da automação, a conta precisa ser **Microsoft Exchange**, para mover e-mails e usar "Enviar como" e os cabeçalhos completos. O `verificar --perfil prod` vai acusar se a conta for ActiveSync.
- **Tutorial de NF:** circulam duas versões (`PYM (Connect)…pdf` e `Passo a Passo_Paymatch_Fornecedor.pptx`). O padrão escolhido segue o PDF, mais frequente no histórico. Confirmar o oficial com a Anelise (S05 / P3).
