# Suíte de regressão e referência antes da limpeza

## Objetivo

Validar o comportamento atual antes de eliminar os candidatos de `ANALISE-codigo-morto.md`. A etapa inicial alterou apenas testes e configuração. As correções posteriores da aplicação são registradas abaixo; os candidatos à limpeza ainda não foram eliminados.

O levantamento inicial, em 08/09/2026, executou 68 testes: **46 passaram e 22 falharam**, em 71,71 segundos. Parte dos testes não selecionava escritório, usava formulários sem request/campos obrigatórios, criava movimentações sem processo e esperava uma API antiga de status do dashboard. Alguns testes de exclusão só verificavam a página de redirecionamento e sequer enviavam o campo `selection` usado pela aplicação.

## Como executar

Com o ambiente de desenvolvimento preparado conforme o README:

```bash
rtk docker compose exec -T web pytest -q
```

O `make test` existente também executa a suíte, criando um container temporário de web. A imagem deve ter as dependências de `requirements/development.txt`.

Para executar apenas os fluxos novos:

```bash
rtk docker compose exec -T web pytest -q tests/test_application_flows.py
```

Para gerar os relatórios completos no container:

```bash
rtk docker compose exec -T web pytest -q --tb=short --junitxml=/tmp/ezl-baseline.xml --cov-report=json:/tmp/ezl-coverage.json
```

Executar as suítes sequencialmente: elas usam o mesmo banco de testes. Não executar dois processos pytest simultaneamente contra esse banco. Não é necessário carregar o seed de demonstração no banco de desenvolvimento.

## Isolamento

- `pytest.ini` seleciona `tests.settings`, que herda as configurações reais da aplicação e substitui apenas infraestrutura de teste.
- O PostgreSQL continua real; pytest-django cria e destrói um banco de testes separado, com migrations e fixtures essenciais. Não se usa SQLite como substituto dos recursos PostgreSQL.
- `conftest.py` instala `unaccent` no banco de testes: em desenvolvimento essa extensão vem do script de inicialização do PostgreSQL, e não é automaticamente copiada para um banco novo.
- Cache e Channels usam backends em memória; e-mails usam o outbox local do Django. Celery executa de forma eager, com transporte em memória e propagação de erros.
- Uploads de cada teste ficam em um diretório temporário próprio; logs usam `/tmp/ezl-tests-logs`. Hash de senha rápido reduz custo de preparação, sem dispensar os validadores de senha.
- `tests/support.py` cria usuário comum, escritório, permissões reais via signals, cliente, pasta padrão, processo, movimentação e sessão. Os testes de permissão não usam superusuário para contornar autorização.

## Contratos cobertos

| Área | Verificações |
|---|---|
| Autenticação e autorização | Redirecionamento de visitantes; permissões do criador limitadas ao próprio escritório; listagem de pastas por escritório; bloqueio de formulário que tenta usar escritório fora da sessão; acesso a questionários e relatório financeiro sem permissão. |
| Pessoas e usuários | Telas existentes; criação HTTP com senha armazenada como hash, pessoa associada e grupo; senha divergente não cria usuário; senha curta produz o erro específico do validador, não um erro incidental de formulário incompleto. |
| Pastas e processos | Criação de pasta com cliente, escritório, numeração e auditoria; validação de campos obrigatórios; criação/edição de processo mantendo a pasta; cadastro/edição de instância; exclusão real dos registros selecionados e preservação dos não selecionados. |
| OS | Criação HTTP com vínculo à movimentação e numeração; aceite; conclusão com resposta de questionário; retorno limpando data de execução; finalização registrando data; formulário com data inválida não altera status; histórico persistido. |
| Dashboard | GET devolve totais por status/escritório e reflete aceite; POST retorna 405, conforme o contrato atual. |
| Anexos | Upload HTTP e conferência dos bytes, autor e vínculo; upload vazio não cria registro; múltiplos anexos em formulário genérico; download com hash correto, hash diferente e arquivo ausente; reprodução do defeito de exclusão. |
| Questionários | Criação/edição HTTP; pendência resolvida por resposta vinculada; conclusão de OS salva resposta e autor; reprodução do defeito de isolamento na edição. |
| Financeiro | Valores a pagar e comissão; consulta restrita ao escritório; OS não concluída excluída; resposta sem filtros vazia; faturamento exige seleção e altera somente OS do escritório atual; XLSX aberto como ZIP/XML com linhas e dados esperados. |
| E-mail | Template real de OS delegada aceita, assunto/conteúdo, destinatários deduplicados, anexo real, redirecionamento de homologação, ausência de destinatários e erro no backend de entrega. O mock de falha está apenas na fronteira de entrega e verifica que ela foi chamada. |

As fixtures de relatórios preparam um retrato financeiro persistido diretamente. Os testes de transição de OS exercitam separadamente as views reais. Nenhum teste depende das 19 definições candidatas à remoção.

## Falhas conhecidas — não são testes ignorados

Três testes continuam executando o comportamento desejado, mas estão marcados com `xfail(strict=True, raises=...)`. A marcação registra defeitos existentes no código atual; não significa que estejam corrigidos. Um resultado inesperadamente aprovado (`XPASS`) faz a suíte falhar, exigindo a retirada/revisão da marcação. Exceções fora do tipo declarado também falham normalmente. A referência inicial tinha quatro xfails; BUG-004 foi corrigido posteriormente.

| ID | Problema confirmado | Reprodutor |
|---|---|---|
| BUG-001 | Edição de pasta acessa `invalid_registry.pk` mesmo quando não existe registro legado inválido, causando `AttributeError`. | `lawsuit/tests.py::FolderTest::test_update_view` |
| BUG-002 | Upload cria `EcmTask`; o FK `EcmTask.ecm` com `PROTECT` impede a exclusão do próprio anexo, e a API retorna falha. | `task/tests/test_task_app.py::EcmTest::test_delete_view` |
| BUG-003 | Filtro de faturamento passa `int` para lookup `isnull`, que exige booleano no Django atual; a consulta gera `ValueError`. | `tests/test_application_flows.py::ApplicationFlows::test_pay_report_unbilled_status_filter` |

Para executar todos esses casos como falhas normais:

```bash
rtk docker compose exec -T web pytest -q --runxfail
```

## Limites

- A suíte cobre os fluxos listados e preserva testes antigos de modelos/telas; não equivale a cobertura completa da aplicação.
- Não foram executados navegador/JavaScript, editor CodeMirror, WebSocket, OAuth externo, worker Celery real ou SMTP real. O contrato de e-mail é validado até o backend local.
- A coleta de cobertura inclui os 11 apps, mas isso não significa que todos tenham testes funcionais próprios. A cobertura antiga incluía apenas core, lawsuit e task, sem medição de branches; os percentuais não devem ser comparados diretamente.
- Permanecem avisos de tabelas com modelo divergente e paginação sem ordenação na suíte antiga. Eles não foram ocultados nem corrigidos nesta etapa.
- O banco de desenvolvimento/produção e as integrações externas não são alvos dos testes.

## Referência inicial, antes das correções

Execução final em 08/09/2026, contra o código da aplicação antes de qualquer limpeza:

| Métrica | Resultado |
|---|---|
| Testes | 107: **103 aprovados e 4 xfailed** |
| Subtestes | 4 aprovados, além dos testes acima |
| Falhas inesperadas / erros | 0 / 0 |
| Avisos | 8, mantidos visíveis |
| Duração com cobertura | 114,86 segundos |
| Linhas executáveis cobertas | **58,33%** — 7.031 de 12.053 |
| Ramificações cobertas | **18,35%** — 403 de 2.196 |
| Indicador combinado do coverage.py | 52,17% |

A cobertura de ramificações ainda é baixa: esta referência protege os contratos listados, mas não permite afirmar que a aplicação inteira esteja validada. A comparação após uma futura remoção deve considerar resultados dos testes e contratos, não apenas o aumento percentual causado pela redução de código.

Foram gerados `/tmp/ezl-baseline.xml` (JUnit) e `/tmp/ezl-coverage.json` no container e copiados para os mesmos caminhos na máquina de trabalho. Esses arquivos são temporários e podem ser reproduzidos pelo comando acima. O JUnit conta os quatro subtestes separadamente e representa os quatro xfails como skipped; o resumo pytest distingue os resultados corretamente.

`graphify update .` foi executado após as mudanças em testes/configuração. O extrator avisou que uma dependência de SQL está ausente; a atualização de AST dos arquivos de código concluiu normalmente. `git diff --check` também passou.

## Correção de BUG-004 — isolamento dos questionários

Em 08/09/2026, `survey/views.py` passou a verificar autenticação e permissão no escritório selecionado em todos os endpoints públicos de questionários. Consultas de objetos para edição são restritas a esse escritório, retornando 404 para objetos de outro escritório. A criação também passou a exigir a permissão que antes estava apenas declarada.

A exclusão em lote valida todos os IDs contra o escritório autorizado antes de qualquer remoção, com transação e bloqueio das linhas selecionadas. Lotes que misturam escritórios, IDs ausentes ou IDs inválidos são rejeitados por inteiro. Questionários protegidos por vínculos permanecem no banco e geram uma mensagem de erro. A validação do formulário impede transferir um questionário enviando outro escritório no POST.

`tests/test_survey_authorization.py` adiciona 15 testes para leitura, criação, edição, exclusão, lote misto, seleção inválida, registros protegidos, falta de permissão, falta de escritório, usuário anônimo e sessão adulterada. O reprodutor original `ApplicationFlows.test_survey_cannot_be_edited_from_another_office` perdeu a marcação xfail e deve passar normalmente. Os testes focados concluíram com **21 aprovados e 11 subtestes aprovados**.

A correção é específica aos endpoints públicos de questionários; não representa uma auditoria de autorização de todos os módulos da aplicação.

Validação completa após a correção: **119 testes aprovados, 3 xfailed, 8 avisos e 11 subtestes aprovados**, sem falhas inesperadas, em 131,86 segundos. `makemigrations --check --dry-run` retornou `No changes detected`; `git diff --check` passou e o Graphify foi atualizado. O JUnit desta execução está em `/tmp/ezl-survey-fixed.xml` no container e na máquina de trabalho.
