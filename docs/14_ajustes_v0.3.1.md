# Ajustes v0.3.1 – leitura tolerante da planilha de escritórios

Origem: 1º teste da operação assistida (10 e 11/11/2026, v0.3.0, perfil `calibracao`).
Os três ciclos executados terminaram em `NÃO EXECUTADO`, antes de ler qualquer e-mail do Outlook
(`estado.db`: 3 ciclos, 0 eventos).

## Causa raiz

`filtros.ler_planilha_escritorios()` montava só um mapa **domínio → escritório** e levantava
`ErroEscritorios` quando um domínio aparecia com nomes diferentes. A planilha da área
(`E-mail sharepoint.xlsx`, colunas `E-mail | Diretório | Escritórios`) é uma lista de **e-mails**,
e 5 domínios tinham mais de um nome: `bicharalaw.com.br`, `bmalaw.com.br`, `machadomeyer.com.br`,
`gmail.com` e `sumaq.com.br`. Uma única linha "conflitante" derrubava o ciclo inteiro.

Problemas de linha que a v0.3.0 não tratava (ou tratava mal):

| Padrão | Ocorrências | v0.3.0 | v0.3.1 |
|---|---|---|---|
| Mesmo domínio com nomes diferentes de escritório | 5 domínios | ciclo não roda | e-mail exato usa o nome da própria linha; nomes equivalentes (`&`/`E`, truncados) são unificados; nomes realmente diferentes → domínio ambíguo, outros endereços ficam em `_Sem escritorio` |
| Escritório `#N/A` (erro do PROCV) | 3 | virava o nome "#N/A" | sem escritório + aviso com a linha |
| Escritório "CNPJ não consta na base de fornecedores" | 4 | virava o nome | sem escritório + aviso (lista configurável) |
| E-mail em domínio público (gmail) | 3 linhas | liberava **qualquer** remetente gmail | só o endereço exato é fornecedor |
| E-mail com espaço no meio (`nome sobrenome@gmail.com`) | 1 | virava `sobrenome@gmail.com` | linha ignorada + aviso |
| Texto de e-mail colado na coluna | 1 | gerava "domínios" lixo (`pagamento.`) | linha ignorada + aviso |
| E-mail repetido | 3 | silencioso | considerado uma vez + aviso |
| Espaço no fim / maiúsculas / caracteres invisíveis | 5 / 7 / 0 | tratado parcialmente | normalizado (NFKC, sem invisíveis, minúsculas) |

## O que mudou

- `filtros.py`: mapa `e-mail → escritório` (prioridade) + `domínio → escritório` (retorno); validação
  de e-mail/domínio; `MapaEscritorios.resumo()`, `linhas_invalidas`, `dominios_ambiguos`.
  `ErroEscritorios` agora só para arquivo/aba/coluna inacessíveis ou planilha sem nenhuma linha válida.
- `FiltroInterno`: e-mail completo em `DOMINIO_INTERNO` vale como caixa (a área preencheu
  `maria.bozzi@...` nesse campo).
- `ciclo.py`: loga o resumo da carga (INFO) e cada linha problemática (WARNING) com o número da linha.
- `verificacao.py`: resumo da planilha; aviso quando `caminho_arquivo_emails` não é um caminho completo
  (a área preencheu `Diretório`).
- `settings.yaml`: `escritorios.valores_sem_escritorio`.
- Sem dependências novas; o modelo da planilha de configuração continua 0.3.0.

## Pendências de negócio (não implementadas)

Ver o relatório do 1º teste: domínios genéricos, nomes divergentes, Sumaq (duas empresas no mesmo
domínio), linhas com `#N/A`/"CNPJ não consta", uso da coluna `Diretório` para o arquivamento e
tutoriais disponíveis offline no OneDrive.

---

# Ajustes v0.3.2 – decisões da área (12/11/2026) e download do OneDrive

| # | Decisão da área | Situação |
|---|---|---|
| 1 | A planilha aceita e-mail exato **e** só o domínio (`@fornecedor.com.br`) | Já era o comportamento da v0.3.1; travado em teste. E-mail de domínio público (gmail) continua valendo só pelo endereço |
| 5 | "CNPJ não consta na base de fornecedores" continua fornecedor | Já era o comportamento da v0.3.1 (fornecedor sem escritório); travado em teste |
| 8 | Salvar o e-mail do fornecedor numa pasta, por Ano > Mês, antes de responder | **Já está no escopo** (D05, seção 6.4 da especificação v0.3.0, entregue na T11). Diferenças em relação ao pedido: hoje salva **depois** da ação, em `<raiz>\<Escritório>\<AAAA-MM>\`. Ajuste aguardando o detalhamento da nomenclatura e do local |
| 9 | Baixar os arquivos de dependência antes de prosseguir | **Implementado** (`nuvem.py`) |

## Download automático (item 9)

- `nuvem.garantir_local()`: arquivo "somente on-line" é lido por inteiro, o que faz o OneDrive
  baixá-lo. A leitura tem tempo limite (`onedrive.tempo_limite_s`, padrão 120 s) para o robô não
  travar com o OneDrive fechado ou sem rede. Depois confere o atributo de novo.
- Usado na planilha de escritórios, nos tutoriais e no `verificar`. Antes de ler os e-mails, o ciclo
  chama `RepositorioTutoriais.preparar()`, que baixa todos os tutoriais configurados e registra
  `Tutoriais: N disponível(is), N baixado(s) do OneDrive agora, N com problema`.
- Não fixa o arquivo no dispositivo (não altera a configuração do OneDrive), não precisa de
  administrador nem de biblioteca nova. `onedrive.baixar_automaticamente: false` volta ao
  comportamento da v0.3.1.
- A pasta de arquivamento só é conferida (pasta não se baixa).
