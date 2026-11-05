# 04 · Guia de execução no Windows

## 1. Pré-requisitos

| Item | Observação |
|---|---|
| Windows 10/11 | Sessão de usuário logada |
| Python 3.10 ou superior | `python --version` |
| **Outlook clássico** | Para os perfis `dev` e `prod`. O **novo Outlook não tem COM**: se a sua máquina usa o novo Outlook, volte para o clássico (botão "Novo Outlook" desligado) |
| Acesso à pasta do projeto | Esta pasta |

## 2. Instalação (uma vez)

```bat
cd "<pasta do projeto>\rpa_duvidas_financeiras"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest
```

O último comando deve terminar com todos os testes passando. O `rpa.bat` usa o `.venv` automaticamente.

> Se o `pip` estiver bloqueado pela rede, peça à TI a liberação do `pypi.org` ou um espelho interno.

## 3. Demonstração (perfil demo, sem Outlook)

```bat
python scripts\preparar_demo.py
rpa.bat previa   --perfil demo
rpa.bat executar --perfil demo
start dados_teste\caixa_simulada\saida\_indice.html
start dados\demo\registro_controle.xlsx
```

`preparar_demo.py` apaga e recria a caixa simulada a cada execução. Com `--todos` ele inclui os 40 e-mails da massa sintética.

## 4. Desenvolvimento na sua caixa (perfil dev)

### 4.1 Preencher a configuração

Em `config\perfis\dev.yaml`:

```yaml
seguranca:
  destinatarios_permitidos:
    - "@empresa.com.br"          # o domínio corporativo
destinatarios:
  analistas_cc:      ["pedro.vieira@empresa.com.br"]
  analise_manual:
    padrao:          ["pedro.vieira@empresa.com.br"]
  avisos_erro:       ["pedro.vieira@empresa.com.br"]
```

Em `config\fornecedores_dev.yaml`, coloque o seu e-mail (e o de colegas que vão mandar testes).

### 4.2 Verificar

```bat
rpa.bat verificar --perfil dev
```

O comando cria a pasta **RPA_Teste** dentro da sua Caixa de Entrada, com as subpastas Respondidos, Encaminhados, Erro e Ignorados, e confere os tutoriais e os modelos. Ele precisa terminar com "Tudo certo para executar."

> O robô **só** lê a pasta `RPA_Teste`. A sua Caixa de Entrada real não é tocada.

### 4.3 Gerar e-mails de teste

```bat
python scripts\enviar_emails_teste_outlook.py --para pedro.vieira@empresa.com.br
```

O script envia 7 e-mails da massa sintética (um por categoria) para você, com `[RPA-TESTE]` no assunto, espera a chegada e move-os para `RPA_Teste`. Também dá para arrastar e-mails manualmente para a pasta, ou pedir a colegas que escrevam. Remetentes que não estão em `fornecedores_dev.yaml` testam o caminho "FORA DA LISTA".

### 4.4 Prévia e execução

```bat
rpa.bat previa   --perfil dev --detalhe
rpa.bat executar --perfil dev
```

Para conferir o resultado:

- **Rascunhos** do Outlook: as respostas no mesmo fio, com a faixa "AMBIENTE DE TESTE", o tutorial anexado e você em CC;
- `RPA_Teste\Respondidos` / `Encaminhados` / `Ignorados` / `Erro`: os originais, com a categoria "RPA - Simulado";
- `dados\dev\registro_controle.xlsx` e `logs\`.

Para repetir o teste de um e-mail: `rpa.bat reprocessar <PROTOCOLO> --perfil dev` e arraste o e-mail de volta para `RPA_Teste`. O protocolo aparece no log, na planilha e no rodapé da mensagem.

### 4.5 Lendo direto da Caixa de Entrada (v0.2.1)

O perfil `dev` lê a **Caixa de Entrada** (`pasta_entrada: "@inbox"`), mas só os e-mails com `[RPA-TESTE]` no assunto recebidos a partir de `recebidos_desde`. Os demais e-mails não são lidos nem alterados.

Como a conta está no Outlook como **Exchange ActiveSync**, o Outlook recusa mover e-mails via COM. Por isso o `dev` usa `mover_apos_tratar: false`: o e-mail tratado fica na Caixa de Entrada, marcado como lido e com a categoria `RPA - …`, e não é lido de novo. O `verificar` mostra o modo em uso e avisa quando a conta é ActiveSync.

- O script `enviar_emails_teste_outlook.py` não tenta mover nada quando a pasta de entrada é a Caixa de Entrada.
- As respostas, encaminhamentos e avisos que o próprio robô gera e que chegam de volta à Caixa de Entrada são **ignorados** (motivo `PROPRIO_RPA`): o robô não responde a si mesmo.
- Para repetir um e-mail: `.\rpa.bat reprocessar <PROTOCOLO> --perfil dev` e, no Outlook, remova a categoria `RPA - …` do e-mail.

## 5. Agendamento (Agendador de Tarefas)

Vale para o piloto, na VM. No dev é opcional.

1. Agendador de Tarefas → **Criar Tarefa** (não "Criar Tarefa Básica").
2. **Geral:** nome `RPA Duvidas Financeiras`. Marque **"Executar somente quando o usuário estiver conectado"**, porque o COM precisa da sessão com o Outlook.
3. **Disparadores:** diariamente, repetir a cada **15 minutos** (`execucao.intervalo_minutos`) por 1 dia, no horário comercial a definir (lacuna L07).
4. **Ações:**
   - Programa: `C:\...\rpa_duvidas_financeiras\rpa.bat`
   - Argumentos: `executar --perfil prod`
   - Iniciar em: `C:\...\rpa_duvidas_financeiras`
5. **Configurações:** "Se a tarefa já estiver em execução: **não iniciar uma nova instância**". O robô também tem trava própria.
6. O Outlook precisa estar aberto e a tela não pode bloquear durante a execução (pedido à TI, S04).

| Código de saída | Significado |
|---|---|
| 0 | Ciclo sem erros |
| 1 | Configuração ou caixa inválida (ver log) |
| 2 | Ciclo concluído, mas com e-mails em Erro |
| 3 | Outro ciclo já em andamento |

## 6. Solução de problemas

| Sintoma | Causa provável | Solução |
|---|---|---|
| "Não foi possível abrir o Outlook via COM" | Novo Outlook, Outlook não configurado ou sessão sem usuário | Use o Outlook clássico, abra-o uma vez e rode na sessão logada |
| Aviso do Outlook "um programa está tentando acessar…" | Proteção do modelo de objetos com antivírus desatualizado | Antivírus em dia ou política da TI liberando o Python |
| "Infelizmente, o Exchange ActiveSync não oferece suporte…" | Conta adicionada como Exchange ActiveSync | `caixa.mover_apos_tratar: false` (v0.2.1) ou conta como Microsoft Exchange (pedido à TI) |
| "Pasta 'X' não existe…" | `criar_pastas_ausentes: false` | Crie a pasta no Outlook ou ligue a criação (só em dev) |
| "Conta/caixa '…' não encontrada" | Caixa não adicionada ao perfil do Outlook | Adicione a conta ou caixa compartilhada; confira `caixa.conta` |
| "Destinatário(s) fora de seguranca.destinatarios_permitidos" | Trava de segurança agiu | Comportamento esperado em dev; confira o domínio |
| "Arquivo existe só na nuvem" | Pasta do OneDrive não está local | Botão direito → "Sempre manter neste dispositivo" |
| "Planilha de controle em uso" | Excel aberto | Feche o Excel; a planilha sai no próximo ciclo ou com `exportar` |
| "Outro ciclo em andamento" | Duas execuções ao mesmo tempo, ou trava antiga | Aguarde. Uma trava com mais de 2 h é removida sozinha |
| Erro estranho de caminho ao rodar `rpa.bat` | Caminho da pasta com caracteres especiais (ex.: aspas “ ” em "Mapeamento ideias “Legal”") | Copie o projeto para um caminho simples, ex.: `C:\RPA\rpa_duvidas_financeiras` (recomendado na VM) |
| E-mail já tratado volta e não gera resposta | Idempotência (RNF01) | Comportamento esperado. Use `reprocessar` só para SIMULADO/ERRO |
