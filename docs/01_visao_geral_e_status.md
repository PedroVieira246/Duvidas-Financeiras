# 01 · Visão geral e status da Frente 1

19/10/2026 · versão 0.1.0 · Pedro Vieira (Área BT)

## 1. O que é a Frente 1

A Frente 1 é a parte do RPA "Dúvidas Financeiras" que automatiza o atendimento às dúvidas que os fornecedores mandam **por e-mail**. O robô:

1. **lê** os e-mails da caixa da automação;
2. **classifica** a dúvida numa das categorias do MVP, com um nível de confiança;
3. **age**: responde com o tutorial anexado ou com o link do Forms, ou encaminha para análise manual com o motivo;
4. **registra** cada e-mail e o move para `Respondidos`, `Encaminhados`, `Ignorados` ou `Erro`.

| Código | Dúvida | Ação |
|---|---|---|
| `TUT_CONNECT` | Acesso ao Connect | Responde com o tutorial anexado |
| `TUT_UPLOAD_NF` | Upload de NF | Responde com o tutorial anexado |
| `TUT_REEMBOLSO` | Reembolso | Responde com o tutorial anexado |
| `TUT_CADASTRO` | Atualização de cadastro | Responde com o tutorial anexado |
| `FORMS_PO` | Envio ou solicitação de PO | Responde com o link do Forms |
| `MANUAL` | Depende do SAP, está fora do escopo, não foi identificada, tem baixa confiança ou o remetente está fora da lista | Encaminha para os analistas com o motivo no assunto |

**Fora do escopo:** SAP, leitura dos anexos recebidos, Paymet/Connect como fonte de resposta, Frente 2 (planilha), chatbot e cadastro de fornecedor novo.

## 2. Estratégia adotada

A especificação aponta a classificação como o maior risco e a massa real como dependência dela. Por isso o desenvolvimento começou pelo que **não depende da área**, com três salvaguardas:

- **Tudo parametrizado.** Caixa, pastas, destinatários, textos, termos e caminhos ficam nos arquivos de `config/`. Migrar da caixa individual do desenvolvedor para a caixa oficial é só trocar de perfil (`dev` → `prod`).
- **Interfaces únicas.** O resto do robô não sabe se a caixa é o Outlook, o Graph ou a caixa simulada, nem se a classificação usa palavras-chave ou IA. Quando a massa e os acessos chegarem, entra uma implementação nova, sem reescrever o fluxo.
- **Caixa simulada.** O ciclo inteiro roda em qualquer máquina, sem Outlook, com dados fictícios. É o que permite testar e demonstrar já.

## 3. Status por função

Legenda: ✅ pronta · ⚠️ pronta com dados simulados (mock) · ⛔ bloqueada · ⏳ não iniciada

| ID | Função | Status | Onde está | O que falta |
|---|---|---|---|---|
| F01 | Configuração e parametrização | ✅ | `config/`, `config.py`, `segredos.py` | Preencher `dev.yaml` (seu e-mail e domínio) |
| F02 | Modelos de dados e interfaces | ✅ | `modelos.py`, `caixa/base.py`, `classificacao/base.py` | — |
| F03 | Conector Outlook COM | ✅ | `caixa/outlook_com.py` | **Rodar na sua máquina** (testado só com objetos simulados) |
| F04 | Leitura e extração | ✅ | `extracao.py` | Calibrar os marcadores com e-mails reais |
| F05 | Filtros | ⚠️ | `filtros.py`, `extracao.py` | Lista oficial de fornecedores (S06) |
| F06 | Classificador por palavras-chave | ⚠️ | `classificacao/palavras_chave.py`, `palavras_chave.yaml` | Massa real para calibrar os termos (S01) |
| F07 | Massa e avaliação | ⚠️ (adiantada) | `tests/dados/`, `scripts/avaliar_classificador.py` | Massa real (S01) |
| F08 | Classificador com IA | ⛔ | — | Provedor aprovado (S02) e massa (S01) |
| F09 | E-mail padronizado (cenário 2) | ⏳ | — | Texto aprovado (S09) e regra de retorno (L01) |
| F10 | Tutoriais | ⚠️ | `tutoriais.py`, `tutoriais*.yaml` | Tutoriais publicados no SharePoint (S05) |
| F11 | Modelos de resposta | ⚠️ | `respostas.py`, `config/modelos/` | Textos aprovados (S09) e link do Forms (S07) |
| F12 | Resposta e modo simulação | ✅ | `ciclo.py`, adaptadores de caixa | — |
| F13 | Encaminhamento para análise manual | ⚠️ | `ciclo.py`, `encaminhamento_manual.html.j2` | Destino real por motivo (S08) |
| F14 | Pós-tratamento (lido, categoria, mover) | ✅ | adaptadores de caixa | — |
| F15 | Registro e auditoria | ✅ | `registro.py` | — |
| F16 | Erros e idempotência | ✅ | `registro.py`, `ciclo.py` | — |
| F17 | Orquestração e agendamento | ⚠️ | `__main__.py` (`--loop`), guia do Agendador | VM definitiva (S04) |
| F18 | Adaptador Microsoft Graph | ⛔ | — | Aplicativo no Entra ID (S12) |
| F19 | Migração para a caixa oficial | ⛔ | `perfis/prod.yaml`, doc 07 | Conta de serviço e VM (S03, S04) |
| F20 | Piloto | ⛔ | — | F19 + lista de fornecedores + meta de acerto |

## 4. O que já dá para demonstrar

1. **Fluxo de ponta a ponta com 12 e-mails fictícios** (`scripts/preparar_demo.py` + `executar --perfil demo`): tutorial, Forms, os quatro motivos de encaminhamento manual, resposta automática ignorada e uma falha que vai para Erro com aviso aos analistas.
2. **Rascunhos no Outlook**, no mesmo fio do e-mail, com o tutorial anexado e os analistas em cópia (perfil dev, na sua caixa).
3. **Prévia sem efeito** (`previa`): mostra a decisão do robô para cada e-mail, sem mexer em nada.
4. **Planilha de controle** com uma linha por e-mail, mais as abas Ciclos e Resumo.
5. **Robustez:** rodar duas vezes não duplica nada, e a falha de um e-mail não para os demais.
6. **Relatório de avaliação do classificador**, pronto para receber a massa real.

O roteiro está em [06_roteiro_demonstracao.md](06_roteiro_demonstracao.md).

## 5. Próximos passos

| Ordem | Ação | Depende de |
|---|---|---|
| 1 | Rodar o perfil dev na sua máquina (doc 04) e registrar o resultado | Você |
| 2 | Enviar à área e à TI as solicitações do doc 08 | Você |
| 3 | Calibrar o classificador com a massa real e definir a meta de acerto | S01 |
| 4 | Trocar os tutoriais fictícios pelos do SharePoint | S05 |
| 5 | Protótipo de IA (F08) e do e-mail padronizado (F09), comparados no relatório de avaliação | S02, S09 |
| 6 | Migração para a caixa oficial e piloto em rascunho | S03, S04 |
