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
| Anexos | Upload HTTP e conferência dos bytes, autor e vínculo; upload vazio não cria registro; múltiplos anexos em formulário genérico; download com hash correto, hash diferente e arquivo ausente; exclusão e limpeza do arquivo após commit; preservação de compartilhados, legados e cópias; rollback; POST/CSRF e isolamento por escritório. |
| Questionários | Criação/edição HTTP; pendência resolvida por resposta vinculada; conclusão de OS salva resposta e autor; reprodução do defeito de isolamento na edição. |
| Financeiro | Valores a pagar e comissão; consulta restrita ao escritório; OS não concluída excluída; resposta sem filtros vazia; faturamento exige seleção e altera somente OS do escritório atual; XLSX aberto como ZIP/XML com linhas e dados esperados. |
| E-mail | Template real de OS delegada aceita, assunto/conteúdo, destinatários deduplicados, anexo real, redirecionamento de homologação, ausência de destinatários e erro no backend de entrega. O mock de falha está apenas na fronteira de entrega e verifica que ela foi chamada. |

As fixtures de relatórios preparam um retrato financeiro persistido diretamente. Os testes de transição de OS exercitam separadamente as views reais. Nenhum teste depende das 19 definições candidatas à remoção.

## Defeitos reproduzidos pela suíte

Os quatro defeitos da referência inicial (BUG-001 a BUG-004) foram corrigidos. Seus reprodutores agora executam sem `xfail`. Isso não significa ausência de outros defeitos: os limites de cobertura continuam válidos. O histórico de cada correção está registrado abaixo.

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

## Correção de BUG-002 — exclusão de anexos

A exclusão individual de `Ecm` remove o vínculo automático com sua própria OS dentro de uma transação. Vínculos com outras OS continuam protegidos por `PROTECT`; se a exclusão falhar, o vínculo removido é restaurado. A remoção física fica a cargo do django-cleanup após commit, preservando o arquivo em caso de rollback.

Anexos legados, registros com `ecm_related` (em qualquer direção) e registros que compartilham o mesmo caminho de arquivo têm sua exclusão bloqueada. Esta etapa libera apenas a exclusão de anexos sem compartilhamento; não implementa desvinculação parcial nem muda a exclusão em lote via QuerySet.

Os endpoints interno e externo exigem POST. O botão da tela envia POST com token CSRF. O endpoint interno exige escritório selecionado, permissões nesse escritório e anexo cuja OS pertença a ele; o externo mantém a validação do hash da OS. Essa verificação não representa uma revisão completa das permissões por papel ou de todos os endpoints de anexos.

O reprodutor original perdeu a marcação xfail. `tests/test_ecm_deletion.py` cobre compartilhamento, legado, cópias relacionadas, caminhos duplicados, rollback, CSRF, método HTTP, escritório diferente, sessão adulterada, ausência de escritório, usuário anônimo e exclusão externa por hash. Antes da correção, os casos focados reproduziram seis falhas; após a correção, os 16 testes focados passaram, antes da inclusão dos casos adicionais de rollback e CSRF.

Validação completa: **133 testes aprovados, 2 xfailed, 8 avisos e 11 subtestes aprovados**, em 141,09 segundos. Os dois xfails restantes são BUG-001 e BUG-003. `makemigrations --check --dry-run` retornou `No changes detected`; `git diff --check` passou e o Graphify foi atualizado. O JUnit está em `/tmp/ezl-ecm-fixed.xml` no container e na máquina de trabalho. A interação JavaScript não foi executada em navegador.

## Correção de BUG-001 — retirada das regras de importação legada

Com a decisão de não realizar novas importações de dados antigos, a edição de pastas deixou de buscar um registro fictício antes de carregar o objeto. O teste `FolderTest.test_update_view` perdeu a marcação xfail. A abertura e o salvamento funcionam sem qualquer registro importado.

A limpeza também removeu `get_invalid_data`, `remove_invalid_registry`, `filter_valid_choice_form`, a exclusão especial da busca genérica e os overrides que existiam apenas para aplicar essas regras. Listagens, APIs, formulários e autocompletes deixam de atribuir significado especial aos nomes terminados em `-INVÁLIDO` e ao código `REGISTRO-INVÁLIDO`. Foram mantidos os filtros existentes de escritório, atividade e relacionamento.

`tests/test_legacy_rule_cleanup.py` cobre abertura e salvamento de pasta sem importação, edição de registro com o antigo marcador, listagem e pesquisa, escolhas de formulário, consultas das APIs de pastas e pessoas, listagem financeira e autocomplete. Os testes verificam também que dados de outros escritórios e opções inativas continuam fora dos resultados onde esses filtros já existiam. As verificações das APIs exercitam os querysets; não substituem testes do OAuth.

Campos históricos, vínculos e proteções de exclusão de anexos permanecem preservados. A decisão e os componentes mantidos estão descritos em `docs/LEGADO.md`.

Validação completa: **143 testes aprovados, 1 xfailed, 11 avisos e 13 subtestes aprovados**, em 151,65 segundos. O único xfail restante é BUG-003, no filtro de faturamento. Os avisos adicionais vêm dos testes que agora alcançam a renderização da pasta, cuja tabela já tinha divergência de modelo; essa divergência não foi corrigida nesta etapa. `makemigrations --check --dry-run` retornou `No changes detected`, `git diff --check` passou e o Graphify foi atualizado. O JUnit está em `/tmp/ezl-legacy-fixed.xml` no container e na máquina de trabalho.

## Correção de BUG-003 — filtro de faturamento

O filtro de OS a pagar passa um booleano ao lookup `parent__billing_date__isnull`: `status=1` gera `True` (não faturadas) e `status=0` gera `False` (faturadas). A opção vazia não adiciona restrição de faturamento e mantém os demais filtros e o comportamento existente de consulta sem filtros.

O reprodutor `ApplicationFlows.test_pay_report_unbilled_status_filter` perdeu a marcação xfail. O novo teste `test_pay_report_billing_status_separates_billed_and_unbilled` prepara OS faturadas e não faturadas simultaneamente e confere os IDs retornados para as três opções. Antes da correção, as opções 0 e 1 reproduziram o erro de tipo; a opção Todas já passava.

Validação focada: **8 testes aprovados e 3 subtestes aprovados**. Suíte completa: **145 testes aprovados, 11 avisos e 16 subtestes aprovados**, sem falhas ou xfails, em 152,08 segundos. Os avisos existentes permanecem visíveis. `git diff --check` passou e o Graphify foi atualizado. O JUnit está em `/tmp/ezl-billing-fixed.xml` no container e na máquina de trabalho.
