# 06 · Roteiro de demonstração (≈ 15 min)

**Objetivo:** mostrar que o robô já funciona de ponta a ponta e que o que falta para o piloto depende da massa de dados e dos acessos (doc 08). A demonstração termina com a cobrança formal.

**Público:** interessados da área financeira, gestor da Área BT e Milton.

## Antes da reunião (5 min)

```bat
.venv\Scripts\activate
python scripts\preparar_demo.py
```

Deixe abertos: um terminal na pasta do projeto, o Explorer em `dados_teste\caixa_simulada` e o doc 08. Se o perfil dev já estiver rodando, prepare também 3 ou 4 e-mails na sua `RPA_Teste` do Outlook.

## Roteiro

| Min | Passo | O que mostrar | Mensagem |
|---|---|---|---|
| 0–2 | Contexto | Tabela de categorias (doc 01) | "O robô lê, classifica e responde ou encaminha. Nada fica sem destino." |
| 2–4 | Caixa de entrada | `dados_teste\caixa_simulada\entrada` com 12 e-mails fictícios | Mistura real: dúvidas mapeadas, SAP, sem tema, resposta automática, remetente desconhecido e uma falha proposital |
| 4–6 | **Prévia** | `rpa.bat previa --perfil demo` | "Antes de agir, dá para ver a decisão de cada e-mail e o motivo." |
| 6–9 | **Execução** | `rpa.bat executar --perfil demo` e depois `saida\_indice.html` | Rascunho com o tutorial anexado, link do Forms, encaminhamento `[MANUAL – SAP]` com a nota interna, aviso de erro |
| 9–10 | Limpeza do texto | O e-mail "RE: Convite portal" | O histórico citava "reembolso" e "pedido de compra", e mesmo assim o robô classificou só pelo texto novo |
| 10–11 | Pastas | Explorer: respondidos / encaminhados / ignorados / erro | Entrada vazia, cada e-mail no seu destino |
| 11–12 | **Planilha** | `dados\demo\registro_controle.xlsx` (abas Registro e Resumo) | Auditoria e base para medir o ganho (hoje o prazo é de uma semana) |
| 12–13 | Segurança | Rodar `executar` de novo (nada acontece) e mostrar a faixa "DEMONSTRAÇÃO" | Nunca responde duas vezes; envio real desligado; trava de destinatários |
| 13–15 | **O que falta** | Doc 08 (tabela de solicitações) | "O fluxo está pronto. Para medir o acerto real e ir para o piloto precisamos de: exemplos de e-mails, tutoriais no SharePoint, lista de fornecedores, textos aprovados e a caixa oficial." |

## Variação com o Outlook (perfil dev)

Troque os passos 4–10 por `rpa.bat executar --perfil dev` e abra a pasta **Rascunhos** no Outlook. A resposta aparece no próprio fio do e-mail, com o anexo, que é exatamente o que o fornecedor receberia.

## Perguntas prováveis

| Pergunta | Resposta |
|---|---|
| "E se o robô errar o tutorial?" | É o erro grave, o indicador que mais pesa. O limite de confiança é conservador e o piloto começa em rascunho, revisado pelos analistas, até a meta de acerto ser atingida. |
| "E os e-mails que ele não entende?" | Vão para os analistas, com o motivo no assunto e a sugestão do robô na nota. |
| "Vai usar IA?" | A interface está pronta. Falta aprovar o provedor (LGPD) e ter exemplos reais para escrever o prompt e comparar com a abordagem atual. |
| "Quando entra em produção?" | Depende das solicitações do doc 08. A migração para a caixa oficial é só trocar a configuração; o código não muda. |
| "Lê os anexos que o fornecedor manda?" | Não. Os anexos só são registrados (fora do MVP). |
