# 07 · Migração para a caixa oficial (F19)

**Princípio:** a migração **não altera código**. Ela consiste em preencher `config/perfis/prod.yaml`, preparar a VM e trocar o perfil no Agendador.

## 1. Pré-requisitos (TI e área)

| # | Item | Solicitação | ☐ |
|---|---|---|---|
| 1 | Conta de serviço ou caixa compartilhada da automação, com licença | S03 | ☐ |
| 2 | VM com Windows, **Outlook clássico** e a caixa configurada, sem bloqueio de tela | S04 | ☐ |
| 3 | Pastas Respondidos, Encaminhados, Erro e Ignorados criadas na caixa, com permissão de categorias | S11 | ☐ |
| 4 | Permissão "Enviar como" ou "Enviar em nome de" para a caixa (se for compartilhada) | S03 | ☐ |
| 5 | Pasta dos tutoriais do SharePoint sincronizada na VM, marcada como "Sempre manter neste dispositivo" | S05 | ☐ |
| 6 | Lista oficial de fornecedores | S06 | ☐ |
| 7 | Link oficial do Forms, destinatários da análise manual e textos aprovados | S07, S08, S09 | ☐ |
| 8 | Regra de centralização definida (regra do Outlook ou automação em cópia) | S10 | ☐ |
| 9 | Python 3.10+ na VM e acesso ao `pypi.org` (ou pacotes copiados) | S04 | ☐ |

## 2. Passo a passo

1. **Copiar o projeto** para a VM, sem as pastas `dados\`, `logs\` e `.venv\`.
2. **Instalar**: `python -m venv .venv`, `.venv\Scripts\activate`, `pip install -r requirements.txt` e `python -m pytest`.
3. **Preencher `config\perfis\prod.yaml`**: `caixa.conta`, `caixa.enviar_em_nome_de`, destinatários e `respostas.link_forms_po`.
4. **Apontar os tutoriais reais**: em `config\tutoriais.yaml`, preencher a `raiz` e conferir os nomes das subpastas e os padrões.
5. **Preencher `config\fornecedores.yaml`** com a lista oficial.
6. **Verificar**: `rpa.bat verificar --perfil prod` deve terminar com "Tudo certo para executar."
7. **Teste de fumaça em rascunho** (`envio_real: false`):
   - enviar 3 e-mails de teste para a caixa oficial (tutorial, Forms, SAP);
   - rodar `rpa.bat previa --perfil prod` e depois `rpa.bat executar --perfil prod`;
   - conferir os rascunhos, as pastas e a planilha `dados\prod\registro_controle.xlsx`.
8. **Agendar** (doc 04, seção 5) com `executar --perfil prod`.
9. **Piloto em rascunho** (etapa 5): os analistas revisam os rascunhos por um período combinado e o resultado é medido.
10. **Liberar o envio real**: com a aprovação dos analistas e a meta de acerto atingida, mudar `execucao.envio_real: true` em `prod.yaml`. Registrar a data e quem aprovou no CHANGELOG.

## 3. O que muda entre dev e prod

| Item | dev | prod |
|---|---|---|
| `caixa.conta` | `""` (sua conta) | caixa da automação |
| `caixa.pasta_entrada` | `@inbox/RPA_Teste` | `@inbox` |
| `caixa.criar_pastas_ausentes` | `true` | `false` |
| `seguranca.destinatarios_permitidos` | domínio interno | vazio (responde a fornecedores) |
| `destinatarios.*` | você | caixa dos analistas |
| `filtros.arquivo_fornecedores` | `fornecedores_dev.yaml` | `fornecedores.yaml` |
| `tutoriais.arquivo` | `tutoriais_demo.yaml` | `tutoriais.yaml` |
| `respostas.faixa_ambiente` | "[AMBIENTE DE TESTE…]" | vazio |
| `registro.*` | `dados/dev/...` | `dados/prod/...` |

## 4. Volta atrás (rollback)

- **Parar:** desabilitar a tarefa no Agendador. Os e-mails ficam na caixa e os analistas assumem.
- **Voltar para rascunho:** `envio_real: false`.
- **Histórico:** `dados\prod\estado.db` mantém o que já foi tratado; nada é respondido de novo ao religar.

## 5. Depois: Microsoft Graph (produção definitiva, F18)

Quando a TI registrar o aplicativo no Entra ID (S12), o adaptador `caixa/graph.py` entra pela mesma interface e o perfil passa a `caixa.tipo: graph`. Assim o robô deixa de depender de sessão logada e do Outlook aberto.
