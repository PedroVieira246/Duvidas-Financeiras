# 12 · Guia de instalação e preenchimento da planilha – v0.3.0 (calibração)

**RASCUNHO – aguardando revisão do financeiro (T16).** Uma página para a instalação assistida (T17) na máquina de cada analista. Base: `Especificacao_Tecnica_v0.3.0_EXE_Calibracao.md`.

## 1. Antes de começar

| Item | Como conferir |
| --- | --- |
| Outlook clássico, Microsoft 365, 64 bits | Arquivo → Conta do Office → Sobre o Outlook. |
| Novo Outlook **desligado** | A chave "Novo Outlook", no canto superior direito, precisa estar desligada. |
| Outlook aberto, com o usuário logado | O robô usa o Outlook da sessão aberta. |
| Pastas do SharePoint sincronizadas | Tutoriais, planilha de escritórios e pasta de arquivamento: botão direito → **Sempre manter neste dispositivo**. |
| Liberação do antivírus ou assinatura do .exe | **A CONFIRMAR com a TI** (ponto em aberto 7). |

## 2. Instalação (cerca de 15 min)

1. Descompacte `RPA_DuvidasFinanceiras_v0.3.0.zip` em uma pasta local, por exemplo `C:\RPA_DuvidasFinanceiras\`. **Não** use uma pasta sincronizada.
2. Abra `config\configuracao.xlsx` e preencha **todas** as células `A_PREENCHER` (seção 3). Salve e feche o arquivo.
3. Dê duplo clique em `RPA_DuvidasFinanceiras.exe` e escolha a opção **1) Verificar configuração**. Corrija o que aparecer como `ERRO`. A mensagem mostra a aba, a linha e a coluna.
   - O resultado também fica salvo em `logs\verificar_AAAA-MM-DD_HHMM.txt`, que é a evidência da instalação.
   - Confira na saída o **tipo da conta**: Microsoft Exchange ou Exchange ActiveSync (ponto em aberto 3).
4. Escolha a opção **2) Prévia**. Ela mostra como cada e-mail seria tratado e **não altera nada**. Confira com o analista.
5. Programe o Agendador de Tarefas (seção 4).

## 3. Preenchimento do `configuracao.xlsx`

| Aba | O que preencher | Ponto em aberto |
| --- | --- | --- |
| Geral | `email_caixa_entrada`: o e-mail da caixa pessoal desta máquina | D03 |
| Geral | `email_destino_padrao`: quem recebe as respostas de teste. Não pode ser o próprio analista. | 4 |
| Geral | `recebidos_desde`: a data da instalação | — |
| Geral | `caminho_planilha_escritorios`, `coluna_dominio` e `coluna_escritorio`. A aba é opcional; vazio = 1ª aba. | 1 |
| Geral | `caminho_arquivo_emails`: pasta dos .msg, por exemplo `arquivo\` ou uma pasta do SharePoint | 2 |
| Geral | `nome_analista`: aparece na assinatura | — |
| Tutoriais | O caminho **completo** do arquivo oficial de cada tutorial. Aceita `%USERPROFILE%`. | 6 |
| Tutoriais | O link do Forms de PO. Vazio = a categoria FORMS_PO vai para análise manual. | 6 |
| Destinatarios | Pelo menos uma linha `AVISO_ERRO`, com quem recebe os avisos de erro | — |
| Filtros | `DOMINIO_INTERNO`: o domínio corporativo | — |

**Abas protegidas:** Geral, Filtros e Listas são protegidas pela BT. Categorias, Palavras_chave, Textos, Tutoriais e Destinatarios ficam abertas ao financeiro.

**Valores que já vêm prontos e só mudam com a BT:**
- `destino_respostas = TESTE`: na v0.3.0 nenhuma resposta vai ao fornecedor.
- `modo_execucao = SIMULACAO`: o robô só gera rascunhos.
- `ia_ligada = N`.
- `acao_manual = CATEGORIZAR`.
- `mover_apos_tratar = N`.
- `marcar_nao_fornecedores = N`: e-mails que não são de fornecedores não são tocados.
- `pular_ja_respondidos = S`.

**Liberar o envio de uma categoria** (a partir de 07/12, depois do critério da seção 12.8, **A CONFIRMAR**: 95% de acerto em pelo menos 20 e-mails):
1. Na aba Categorias, troque **Liberada para envio** para `S` e preencha a **Data da liberação**.
2. Na aba Geral, troque `modo_execucao` para `REAL`.

As respostas continuam indo **só** para o destino padrão. Um "Tutorial errado" no retorno, depois da data de liberação, bloqueia a categoria sozinho. Para liberar de novo, preencha uma data nova.

## 4. Agendador de Tarefas do Windows

1. Abra o Agendador de Tarefas e clique em **Criar Tarefa** (não use "Criar Tarefa Básica").
2. Aba **Geral**: nome "RPA Dúvidas Financeiras". Marque **Executar somente quando o usuário estiver conectado**.
3. Aba **Disparadores**:
   - Diariamente às **8h00**, nos dias úteis (**A CONFIRMAR com o financeiro**, ponto em aberto 5).
   - Repetir a tarefa a cada **15 minutos** (o mesmo valor de `intervalo_minutos`), por **10 horas**.
4. Aba **Ações**:
   - Programa: o caminho completo de `RPA_DuvidasFinanceiras.exe`.
   - Argumentos: `executar`.
   - Iniciar em: a pasta do .exe.
5. Aba **Configurações**: marque **Não iniciar uma nova instância** se a tarefa já estiver em execução.

O robô também tem uma trava própria contra dois ciclos ao mesmo tempo.

## 5. No dia a dia

- **Planilha de controle:** opção 5 do menu, ou `dados\registro_controle.xlsx`.
  - Preencha só as colunas laranja do fim: Avaliação, Categoria correta, Observação, Tempo manual (min), Revisado por e Data da revisão.
  - O robô lê essas colunas a cada ciclo e não perde o que foi preenchido.
  - Se a planilha estiver aberta, a atualização fica para o próximo ciclo.
- **E-mails tratados:** ficam na Caixa de Entrada, com a categoria `RPA - …`. Não são movidos.
  - E-mails que o analista já respondeu ou encaminhou não recebem resposta do robô.
- **Arquivamento:** se falhou, a coluna "Arquivado em" mostra `FALHA`. Para refazer, rode `RPA_DuvidasFinanceiras.exe arquivar-pendentes`.
