# 05 · Testes e qualidade

## 1. Testes automatizados

```bat
python -m pytest            :: todos
python -m pytest -k ciclo   :: só um grupo
```

| Arquivo | O que cobre |
|---|---|
| `test_config.py` | Mescla de perfis, expansão de variáveis (`%VAR%`, `${VAR}`), validação, trava obrigatória fora de prod, **ausência de endereços/caminhos fixos no código** |
| `test_extracao.py` | HTML → texto, corte de histórico (PT/EN, Outlook, Gmail), assinatura, aviso legal, detecção de resposta automática (classe, cabeçalho, assunto), lista de destinatários permitidos |
| `test_classificacao.py` | Cada categoria, SAP e fora do escopo indo para MANUAL, nenhum termo, peso do assunto, palavra inteira, dois temas reduzindo a confiança, regressão na massa sintética |
| `test_tutoriais_respostas.py` | Arquivo mais recente, pasta ou arquivo ausente, arquivo vazio, limite de tamanho, renderização de todos os modelos, escape de HTML |
| `test_ciclo.py` | **De ponta a ponta com a caixa simulada:** destinos corretos, CC, anexo, rascunho × envio real, planilha, idempotência, falha ao mover depois de responder, erro com aviso sem parar o ciclo, reprocessamento, tutorial ausente, trava de segurança, baixa confiança, trava de execução, comandos `executar` / `verificar` / `previa` |
| `test_validacao_ia.py` (v0.2.0) | Regras V1–V10: JSON válido, cerca Markdown, texto extra, campos/tipos, listas fechadas, limites de tamanho |
| `test_decisao_ia.py` (v0.2.0) | Regras D1–D7 (uma por regra), ordem das regras, resposta automática, `categorias_ia.yaml` inválido |
| `test_mascaramento.py` (v0.2.0) | CNPJ com e sem pontuação, CPF, agência/conta, PIX, telefones, truncamento |
| `test_classificador_ia.py` (v0.2.0) | `ClassificadorIA` com provedor simulado: sucesso, timeout com 2 novas tentativas (2 s/4 s), JSON inválido com correção, inválido persistente, falhas seguidas, montagem e mascaramento do prompt, *prompt injection*, provedor HTTP genérico com servidor falso |
| `test_anexo_a.py` (v0.2.0) | Prompt idêntico ao Anexo A; os 9 exemplos passam pela validação e pela decisão |
| `test_filtros_extracao_v020.py` (v0.2.0) | `historico_resumido` (E1); filtros de e-mail interno e spam (E2), inclusive no ciclo |
| `test_registro_migracao.py` (v0.2.0) | Colunas novas, migração de um banco v0.1.0, tabela `respostas_ia`, planilha |
| `test_ciclo_ia.py` (v0.2.0) | Ciclo completo com `tipo: ia`: 1 resposta com tutorial + 1 encaminhamento com resumo, IA indisponível, 5 falhas seguidas, JSON inválido, CLI, reversibilidade |
| `test_verificar_avaliar.py` (v0.2.0) | `verificar` (prompt, mapeamento, credencial, lista vazia em prod) e `avaliar_classificador.py --limites` |
| `test_outlook_com.py` | Adaptador Outlook com **objetos COM simulados**: criação de pastas em `@inbox`, conversão do e-mail, remetente Exchange, imagem inline, resposta em rascunho com CC e anexo, encaminhamento, mover e categorizar, só não lidos |

> **Limitação:** o adaptador COM foi testado com objetos simulados. O teste definitivo é rodar o perfil `dev` na sua máquina (doc 04, seção 4) e marcar o resultado na tabela abaixo.

### Teste de aceite manual no Outlook (perfil dev)

| # | Cenário | Esperado | Resultado |
|---|---|---|---|
| M1 | `verificar --perfil dev` | Cria `RPA_Teste` e as subpastas; "Tudo certo" | ☐ |
| M2 | E-mail "Acesso ao Connect" | Rascunho no mesmo fio, com o tutorial anexado, você em CC e a faixa de teste; original em Respondidos com a categoria "RPA - Simulado" | ☐ |
| M3 | E-mail "Pedido de compra" | Rascunho com o link do Forms, sem anexo | ☐ |
| M4 | E-mail "Quando vou receber o pagamento?" | Rascunho de encaminhamento `[MANUAL – SAP]` com a nota interna | ☐ |
| M5 | E-mail de colega fora de `fornecedores_dev.yaml` | `[MANUAL – FORA DA LISTA]` | ☐ |
| M6 | E-mail HTML com histórico e assinatura (responda a um e-mail antigo) | `previa --detalhe` mostra só o texto novo | ☐ |
| M7 | Resposta automática de ausência (ative o "Fora do escritório" num colega) | Original em Ignorados, sem rascunho | ☐ |
| M8 | Rodar `executar` duas vezes seguidas | Nenhum rascunho duplicado | ☐ |
| M9 | Renomear a pasta de um tutorial fictício e enviar a dúvida dela | E-mail em Erro e rascunho de aviso | ☐ |
| M10 | E-mail com anexo PDF | Planilha com "Tem anexos = sim"; anexo não aberto | ☐ |

## 2. Massa de teste

### Massa sintética (disponível)

`tests/dados/massa_emails_sintetica.csv` tem 40 e-mails **inventados**, cobrindo as 6 categorias, casos de SAP, fora do escopo, sem tema, texto informal e um caso com dois temas.

> Os termos do classificador e a massa sintética foram escritos juntos. **Acertar 100% nela só prova que a mecânica funciona, não que o robô vai acertar e-mails reais.**

### Massa real (aguardando S01)

Formato pedido à área (seção 4 da especificação), salvo como `tests/dados/massa_emails.csv`:

| Coluna | Conteúdo |
|---|---|
| `id` | Identificador sequencial |
| `assunto` | Assunto do e-mail |
| `corpo` | Texto do e-mail, **sem dados que identifiquem o fornecedor** (trocar nomes, CNPJ e números de NF/pedido) |
| `categoria_esperada` | `TUT_CONNECT`, `TUT_UPLOAD_NF`, `TUT_REEMBOLSO`, `TUT_CADASTRO`, `FORMS_PO` ou `MANUAL` |

Sugestão (premissa P05): pelo menos 10 a 20 exemplos por categoria, incluindo os casos difíceis.

## 3. Avaliação do classificador

```bat
python scripts\avaliar_classificador.py --massa tests\dados\massa_emails.csv --perfil dev
```

O script gera `relatorios\avaliacao_<data>.md` e `.csv` com:

- **acerto geral e por categoria**;
- **% que vai para análise manual** (quanto menor, maior o ganho);
- **erros graves**: tutorial ou link errado enviado ao fornecedor. É o indicador que mais pesa.

Resultado atual na massa sintética (limite 0,70): 40/40 acertos, 35% para manual, 0 erros graves. Com limite 0,55 aparecia 1 erro grave (o e-mail com dois temas), por isso o limite inicial é 0,70.

### Como calibrar com a massa real

1. Rode a avaliação e abra o `.csv` (separador `;`).
2. Para cada erro, confira a coluna `motivo`, que mostra os termos que pontuaram.
3. Ajuste `config/palavras_chave.yaml`: inclua os termos que os fornecedores usam, reduza o peso de termos ambíguos e mova para `MANUAL_SAP` o que depende de consulta.
4. Ajuste `classificacao.limite_confianca` para equilibrar **zero erro grave** com **o menor % manual possível**.
5. Rode de novo. O mesmo relatório vai comparar as abordagens de IA (F08) e de e-mail padronizado (F09).

A meta de acerto para liberar o envio real ainda precisa ser definida com a área (S13).
