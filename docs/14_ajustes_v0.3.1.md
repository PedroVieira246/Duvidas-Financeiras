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
