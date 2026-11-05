# 08 · Solicitações à área e à TI

Base para a cobrança formal. Atualize a coluna **Situação** a cada retorno.

19/10/2026 · RPA Dúvidas Financeiras · Frente 1

## 1. Quadro de solicitações

| ID | Item solicitado | A quem | Finalidade | Desbloqueia | Urgência | Situação |
|---|---|---|---|---|---|---|
| S01 | **Exemplos reais de e-mails de fornecedores**, anonimizados, com a categoria esperada (formato no doc 05, seção 2) | Anelise | Calibrar o classificador, escrever o prompt da IA e medir o acerto | F06, F07, F08, F09 | **Alta** | Pendente |
| S02 | **Aprovação de provedor de IA** para processar texto de e-mails de fornecedores (segurança e LGPD) | Segurança da Informação / TI | Viabilizar o cenário 1 (IA com prompt) | F08 | **Alta** (prazo longo) | Pendente |
| S03 | **Conta de serviço ou caixa compartilhada** da automação, com licença e permissão "Enviar como/em nome de" | TI | Caixa oficial onde o robô vai operar | F19, F20 | **Alta** (prazo longo) | Pendente |
| S04 | **VM Windows com Outlook clássico** e a caixa configurada, sem bloqueio de tela, com Python 3.10+ | TI | Execução agendada do piloto | F17, F19 | **Alta** | Pendente |
| S05 | **Tutoriais publicados no SharePoint**, com subpastas e nomes padronizados, e confirmação de que o envio é por anexo | Anelise | Anexar o arquivo certo a cada categoria | F10, F12 | Média/Alta | Pendente |
| S06 | **Lista de e-mails/domínios dos fornecedores** atendidos | Anelise | Filtro de remetente e regra do Outlook | F05, F20 | Média | Pendente |
| S07 | **Link oficial do Forms** de solicitação de PO | Área financeira | Resposta `FORMS_PO` | F11 | Média | Pendente |
| S08 | **Destinatários**: caixa dos analistas em cópia e destino do caso manual (tributário / demais matérias) | Área financeira | Cópia nas respostas e encaminhamento por motivo | F12, F13 | Média | Pendente |
| S09 | **Textos aprovados** das respostas por categoria e do e-mail padronizado | Área financeira | Trocar os textos provisórios | F11, F09 | Média | Pendente |
| S10 | **Forma de centralização** dos e-mails na caixa da automação (regra do Outlook × automação em cópia) | Área + TI | Definir como os e-mails chegam ao robô | F19, F20 | Média | Em aberto |
| S11 | **Pastas e categorias** liberadas na caixa oficial e definição do cofre de credenciais | TI | Pós-tratamento (RF09) e segurança | F14, F19 | Média | Pendente |
| S12 | **Aplicativo no Entra ID** com `Mail.ReadWrite` e `Mail.Send`, restrito à caixa da automação | TI | Produção sem sessão logada (Graph) | F18 | Baixa (pedir já, prazo longo) | Pendente |
| S13 | **Volume real e picos** de e-mails e **meta de acerto** para liberar o envio real | Área financeira | Dimensionamento e critério de saída do piloto | F17, F20 | Baixa agora | Pendente |

## 2. O que já está pronto, independentemente dessas entregas

- Fluxo completo de leitura, classificação, resposta ou encaminhamento, movimentação e registro, demonstrável com dados fictícios.
- Modo simulação (só rascunhos) e trava de destinatários.
- Planilha de controle e log de auditoria.
- Migração preparada: trocar de caixa é só configuração.

Ver os docs 01 e 06.

## 3. Modelos de e-mail para a cobrança

### Para a área financeira (S01, S05–S09, S13)

> **Assunto:** RPA Dúvidas Financeiras – Frente 1 pronta para testes: itens necessários para o piloto
>
> Olá, Anelise e equipe,
>
> A primeira versão do robô da Frente 1 (triagem e resposta de e-mails) já funciona de ponta a ponta com dados de teste: lê o e-mail, identifica o tema, prepara a resposta com o tutorial ou o link do Forms, encaminha o que não é mapeado e registra tudo numa planilha de controle. *(anexar prints ou convidar para a demonstração)*
>
> Para calibrar o robô com casos reais e seguir para o piloto, precisamos de:
>
> 1. **Exemplos de e-mails de fornecedores** (de preferência 10 a 20 por tipo de dúvida), sem dados que identifiquem o fornecedor, com o tipo de dúvida de cada um;
> 2. **Tutoriais publicados no SharePoint**, nas subpastas combinadas;
> 3. **Lista de e-mails dos fornecedores** atendidos;
> 4. **Link oficial do Forms** de solicitação de PO;
> 5. **Caixas de destino**: analistas em cópia e encaminhamento manual (tributário e demais matérias);
> 6. **Aprovação dos textos** das respostas (seguem os rascunhos);
> 7. **Volume médio e picos** de e-mails e a **meta de acerto** para liberar o envio.
>
> Os itens 1 e 2 são os mais urgentes: sem eles não conseguimos medir o acerto do robô. Podemos combinar uma data até **___/___**?

### Para a TI (S02–S04, S11, S12)

> **Assunto:** RPA Dúvidas Financeiras – solicitação de ambiente para o piloto
>
> Prezados,
>
> Para o piloto da automação de respostas a fornecedores (Área BT), solicitamos:
>
> 1. **Conta de serviço ou caixa compartilhada** da automação, com licença de e-mail e permissão de envio em nome dela;
> 2. **VM Windows** com Outlook clássico e essa caixa configurada, sem bloqueio de tela durante a execução, com Python 3.10+;
> 3. **Pastas e categorias** do Outlook liberadas na caixa (Respondidos, Encaminhados, Erro, Ignorados);
> 4. **Orientação sobre o cofre de credenciais** a usar;
> 5. **Aplicativo no Entra ID** (Microsoft Graph, `Mail.ReadWrite` e `Mail.Send` de aplicação, restrito a essa caixa), para a fase de produção;
> 6. **Avaliação de provedor de IA** aprovado para processar o texto dos e-mails (LGPD).
>
> Os itens 1 e 2 bloqueiam o piloto; o 5 e o 6 têm prazo maior e por isso já estão sendo pedidos agora. A automação não guarda credenciais no código e começa em modo rascunho, sem envio real.
