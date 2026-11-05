# RPA Dúvidas Financeiras – Frente 1 (triagem e resposta de e-mails)

Robô em Python que **lê** os e-mails de dúvidas de fornecedores, **classifica** o tema e **age**: responde com o tutorial anexado ou com o link do Forms, ou encaminha para análise manual com o motivo. Usa o Microsoft Outlook clássico (pywin32) no MVP.

> Versão 0.3.0 · 05/11/2026 · Área BT · Pedro Vieira
> **Novidade da 0.3.0:** executável (`RPA_DuvidasFinanceiras.exe`) configurado pela planilha `config\configuracao.xlsx`, para a calibração na máquina do analista (perfil `calibracao`): respostas só para o e-mail destino padrão, arquivamento .msg, retorno manual na planilha de controle e envio liberado por categoria. Ver [docs/12_guia_instalacao_v0.3.0.md](docs/12_guia_instalacao_v0.3.0.md) e [docs/13_ajustes_v0.3.0.md](docs/13_ajustes_v0.3.0.md).
>
> Versão 0.2.0 · 23/10/2026 · Área BT · Pedro Vieira
> Bases: `Especificacao_MVP_RPA_DuvidasFinanceiras.md` (15/10/2026) e `especificacao_funcional_classificacao.md` (22/10/2026 – classificação por IA)

**Novidade da 0.2.0:** classificação por **IA generativa (F08)**, com regras fixas de decisão (D1–D7), mascaramento de dados sensíveis e resumo da dúvida para o analista. **A IA vem desligada**: o padrão continua `classificacao.tipo: palavras_chave` e, assim, o robô se comporta igual à v0.1.0. O provedor corporativo de IA ainda não foi definido (PA08); por enquanto só existe o provedor **simulado**, que não usa rede. Detalhes em [CHANGELOG.md](CHANGELOG.md).

## Situação atual

As etapas 1 a 3 da especificação (seção 9) estão implementadas e testadas com dados simulados:

| Função | Situação |
|---|---|
| F01 Configuração e perfis (dev / demo / prod) | ✅ pronta |
| F02 Interfaces `CaixaEmail` e `Classificador` | ✅ pronta |
| F03 Conector Outlook COM | ✅ pronta · testada com objetos simulados, **falta o teste na sua máquina** |
| F04 Leitura e extração (HTML, histórico, assinatura, resposta automática) | ✅ pronta |
| F06 Classificador por palavras-chave | ⚠️ pronto com termos iniciais · **aguarda a massa real** · continua o **padrão** |
| F08 Classificador por IA (E1–E8, D1–D7) | ⚠️ pronto e testado com **IA simulada** · **aguarda o provedor corporativo (PA08)** e a calibração com a massa real |
| E2 Filtros de e-mail interno e spam | ✅ prontos · desligados por padrão (ligados no perfil `demo_ia`) |
| F10 / F11 Tutoriais e modelos de resposta | ⚠️ prontos com tutoriais fictícios e textos provisórios |
| F12 / F13 / F14 Resposta, encaminhamento e pós-tratamento, com modo simulação | ✅ prontos |
| F15 / F16 Registro, planilha de controle, idempotência e erros | ✅ prontos |

Os detalhes estão em [docs/01_visao_geral_e_status.md](docs/01_visao_geral_e_status.md), e o que falta da área e da TI está em [docs/08_solicitacoes_area_e_ti.md](docs/08_solicitacoes_area_e_ti.md).

## Começo rápido: demonstração sem Outlook (qualquer máquina)

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt

python scripts\preparar_demo.py
rpa.bat previa   --perfil demo
rpa.bat executar --perfil demo
```

Para ver o resultado:

- `dados_teste\caixa_simulada\saida\_indice.html`: as respostas e os encaminhamentos gerados (abrir no navegador);
- `dados\demo\registro_controle.xlsx`: a planilha de controle;
- `logs\rpa_AAAA-MM-DD.log`: o log técnico.

## Na sua caixa do Outlook (perfil dev)

1. Preencha os campos `<PREENCHER...>` em `config\perfis\dev.yaml` e `config\fornecedores_dev.yaml`.
2. Rode `rpa.bat verificar --perfil dev`. Ele cria a pasta `RPA_Teste` e as subpastas dela na sua Caixa de Entrada.
3. Gere e-mails de teste com `python scripts\enviar_emails_teste_outlook.py --para seu.email@empresa.com.br`.
4. Confira o que o robô faria, sem que ele faça nada: `rpa.bat previa --perfil dev`.
5. Execute com `rpa.bat executar --perfil dev`. Só são gerados **rascunhos**, porque o envio real fica desligado em dev.

O passo a passo completo está em [docs/04_guia_execucao_windows.md](docs/04_guia_execucao_windows.md).

## Classificação por IA (F08)

Demonstração sem rede e sem IA real (provedor simulado):

```bat
python scripts\preparar_demo.py --ia
rpa.bat previa   --perfil demo_ia
rpa.bat executar --perfil demo_ia
```

Para ligar a IA num perfil real, quando o provedor for aprovado (PA08):

1. No perfil (`config\perfis\<perfil>.yaml`): `classificacao.tipo: ia` e, em `classificacao.ia.provedor`, `tipo: http_generico` com `endpoint`, `modelo` e, se preciso, os campos/caminhos do contrato do provedor (ver [docs/03](docs/03_configuracao.md#classificacaoia-v020)).
2. Cadastre a credencial: `python -m keyring set rpa_duvidas ia_api_key` (ou a variável `RPA_IA_API_KEY`).
3. Rode `rpa.bat verificar --perfil <perfil>`: ele confere prompt, `categorias_ia.yaml`, mapeamento categoria → tutorial e credencial.
4. Calibre o limite com a massa real: `python scripts\avaliar_classificador.py --massa <massa.csv> --perfil <perfil> --classificador ia --limites 0.70,0.75,0.80,0.85,0.90`.
5. Piloto em rascunho (`envio_real: false`) até zero erros graves. Para voltar ao classificador antigo: `classificacao.tipo: palavras_chave`.

O texto gerado pela IA **nunca** vai ao fornecedor: a resposta vem sempre dos modelos `TUT_*.html.j2`. O resumo da IA vai só na nota interna ao analista.

## Comandos

| Comando | O que faz |
|---|---|
| `rpa.bat executar --perfil X` | Executa um ciclo. Com `--loop`, repete a cada `execucao.intervalo_minutos` |
| `rpa.bat previa --perfil X` | Mostra como cada e-mail pendente seria tratado, **sem agir** |
| `rpa.bat verificar --perfil X` | Confere a configuração, os tutoriais, os modelos e a conexão com a caixa |
| `rpa.bat reprocessar PROTOCOLO --perfil X` | Libera um e-mail SIMULADO ou com ERRO para ser tratado de novo |
| `rpa.bat exportar --perfil X` | Gera de novo a planilha de controle |
| `python scripts\avaliar_classificador.py --massa arquivo.csv` | Mede o classificador (acerto, % manual, erros graves) |
| `python scripts\avaliar_classificador.py --classificador ia --limites 0.70,0.75,0.80,0.85,0.90` | Mede a IA em vários limites de confiança (calibração – seção 6.2) |
| `python scripts\preparar_demo.py --ia` | Prepara a demonstração da IA (perfil `demo_ia`) |
| `python -m pytest` | Roda os testes automatizados (219) |

## Estrutura

```text
rpa_duvidas_financeiras/
├── config/                 tudo o que muda sem mexer no código
│   ├── settings.yaml       base comum
│   ├── perfis/             dev.yaml · demo.yaml · prod.yaml
│   ├── tutoriais*.yaml     categoria → pasta/arquivo do tutorial
│   ├── palavras_chave.yaml termos e pesos do classificador
│   ├── categorias_ia.yaml  categorias C03…C99 → tutorial e habilitação (IA)
│   ├── prompts/            prompt versionado da IA (classificacao_v1.txt)
│   ├── ia_simulada.yaml    regras do provedor de IA SIMULADO (testes e demo)
│   ├── fornecedores*.yaml  lista de remetentes atendidos
│   └── modelos/            textos das respostas (Jinja2/HTML)
├── src/rpa_duvidas/
│   ├── __main__.py         linha de comando
│   ├── config.py           carga, mescla e validação da configuração
│   ├── modelos.py          EmailRecebido, Classificacao, Resultado
│   ├── caixa/              interface CaixaEmail + outlook_com.py + arquivo.py (simulada)
│   ├── classificacao/      interface Classificador + palavras_chave.py + IA:
│   │                         ia.py · validacao_ia.py · decisao_ia.py · provedores_ia.py
│   ├── mascaramento.py     CNPJ/CPF/banco/PIX/telefone antes da IA
│   ├── extracao.py         HTML → texto, histórico, assinatura, respostas automáticas
│   ├── filtros.py          lista de fornecedores, e-mail interno, spam (SCL)
│   ├── tutoriais.py        localiza e valida o anexo
│   ├── respostas.py        monta as mensagens
│   ├── registro.py         log, SQLite de estado, planilha, trava
│   ├── ciclo.py            orquestra o tratamento de cada e-mail
│   └── segredos.py         credenciais via Gerenciador de Credenciais (credencial da IA)
├── scripts/                demo, e-mails de teste no Outlook, avaliação do classificador
├── tests/                  testes automatizados + massa sintética
├── dados_teste/tutoriais/  tutoriais FICTÍCIOS
└── docs/                   documentação da Frente 1
```

## Documentação

| # | Documento | Para quem |
|---|---|---|
| 01 | [Visão geral e status](docs/01_visao_geral_e_status.md) | Todos |
| 02 | [Arquitetura](docs/02_arquitetura.md) | Desenvolvimento |
| 03 | [Configuração](docs/03_configuracao.md) | Desenvolvimento / sustentação |
| 04 | [Guia de execução no Windows](docs/04_guia_execucao_windows.md) | Desenvolvimento / sustentação |
| 05 | [Testes e qualidade](docs/05_testes_e_qualidade.md) | Desenvolvimento |
| 06 | [Roteiro de demonstração](docs/06_roteiro_demonstracao.md) | Apresentação aos interessados |
| 07 | [Migração para a caixa oficial](docs/07_migracao_caixa_oficial.md) | Desenvolvimento / TI |
| 08 | [Solicitações à área e à TI](docs/08_solicitacoes_area_e_ti.md) | Gestão / cobrança formal |
| 09 | [Rastreabilidade de requisitos](docs/09_rastreabilidade_requisitos.md) | Gestão / aceite |
| 10 | [Decisões, premissas e lacunas](docs/10_decisoes_premissas_lacunas.md) | Todos |
| — | [Histórico de versões](CHANGELOG.md) | Todos |

## Regras de segurança embutidas

- **Envio real desligado por padrão** (`execucao.envio_real: false`): nesse modo o robô só gera rascunhos.
- **Trava de destinatários** fora de produção: o robô só gera mensagens para os domínios listados em `seguranca.destinatarios_permitidos`. Qualquer outro destinatário bloqueia a ação e o e-mail vai para Erro.
- **Nenhum e-mail é respondido duas vezes**: o estado fica gravado *antes* do envio e é conferido a cada ciclo.
- **Nenhum endereço, pasta ou credencial no código**: um teste automatizado barra isso.
- Os anexos recebidos nunca são abertos, só registrados (RF02).
- **IA:** a IA sugere e o RPA decide (D1–D7); na dúvida, vai para manual. Dados sensíveis são mascarados antes do envio, o conteúdo do e-mail vai entre delimitadores como dado e o texto da IA nunca chega ao fornecedor.
