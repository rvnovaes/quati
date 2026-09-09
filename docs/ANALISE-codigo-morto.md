# Análise de candidatos à eliminação

Data: 08/09/2026. Escopo: candidatos identificados no levantamento com Graphify, dependências imediatas e duplicação de CodeMirror. Nenhum fonte da aplicação foi alterado ou removido.

## Resultado

Recomenda-se uma primeira limpeza com 19 definições Python sem consumidores encontrados e um `raise` inalcançável. As definições somam 311 linhas, sem contar linhas em branco entre elas e limpeza de imports. A cópia de CodeMirror em `dashboard/static/codemirror` também pode ser retirada na configuração atual de estáticos.

Isso não autoriza excluir os apps `etl`, `billing`, `dashboard` ou os modelos usados pelas classes listadas.

## Evidências e método

- Graphify: consulta inicial aos candidatos e suas relações, seguida de conferência no código atual. A existência de uma aresta por herança ou import do módulo não foi tratada como prova de uso da classe.
- Busca por nomes completos nos arquivos versionados Python, HTML, JavaScript, JSON, YAML, shell, configurações e documentação, incluindo migrations e fixtures. Os nomes aparecem apenas nas definições, exceto `OfficeToPaySerializer`, consumido exclusivamente por outro candidato.
- Inspeção dos mecanismos dinâmicos: o dashboard executa código armazenado no banco; as buscas genéricas importam modelos ou montam expressões de consulta. Não foi localizado um registro dinâmico dos candidatos.
- Banco local: consulta em transação `READ ONLY`, com limite de 15 segundos por instrução; 194 campos CharField/TextField/JSONField em 82 tabelas/modelos do projeto. Nenhuma ocorrência dos 20 nomes pesquisados (19 candidatos à primeira limpeza e a tarefa Celery `delete_imported_xls`). Foram retornadas apenas contagens, sem conteúdo dos registros.
- Django carregado no container local: nenhum candidato encontrado nas classes ou bases das views das rotas resolvidas; `ACCOUNT_FORMS` está vazio.
- Simulação: um importador temporário retirou as 19 definições da AST apenas na memória de um novo processo. `django.setup()`, imports dos módulos envolvidos e `run_checks()` concluíram; a lista de problemas foi vazia. Arquivos, processos de serviço e registros do banco não foram modificados pela simulação.
- Estáticos: verificação com os finders reais do Django para cada um dos 323 caminhos da cópia de CodeMirror em `dashboard`.

## Primeira limpeza recomendada

As linhas referem-se ao código antes de qualquer remoção.

| Arquivo / linha | Definições | Justificativa e limite da remoção |
|---|---|---|
| `task/views.py:1786` | Segundo `raise Http404` consecutivo | Inalcançável: o anterior sempre encerra esse caminho. Preservar o primeiro. |
| `lawsuit/views.py:180,192` | `FolderCreateView`, `FolderUpdateView` | Sem consumidores. As rotas `folder_add` e `folder_update` usam `FolderLawsuitCreateView` e `FolderLawsuitUpdateView`. Preservar `FolderForm` e os modelos. |
| `ecm/utils.py:8,26` | `combine_chunks`, `save_upload` | Sem chamadas. `UploadView` salva `Attachment` diretamente; o fluxo dos formulários usa `attachment_form_valid`. Remover apenas essas funções, não o módulo. |
| `ecm/views.py:49` | `AttachmentFormMixin` | Nenhuma subclasse ou rota usa o mixin. O mixin ativo de formulário em core usa o decorator `attachment_form_valid`. |
| `task/serializers.py:13,124` | `PersonAskedByDefault`, `TaskToPaySerializer` | Sem consumidores. As views atuais de contas a pagar usam `TaskToPayDashboardSerializer`. |
| `task/utils.py:196` e `task/serializers.py:118` | `get_offices_to_pay`, `OfficeToPaySerializer` | A função não tem chamadas e é a única consumidora do serializer. Remover ambos no mesmo lote. |
| `core/forms.py:143,466` | `ContactForm`, `RegisterNewUserForm` | Sem consumidores ou configuração de formulário do allauth. O CRUD de usuário usa `UserCreateForm`; não remover esse formulário nem seu import de `UserCreationForm`. |
| `task/utils.py:74` | `task_send_mail` | Sem chamadas. O envio ativo usa `TaskMail` em `task/signals.py`. Preservar o sistema de e-mail, suas classes e templates. |
| `etl/tables.py:5` | `DashboardErrorStatusTable` | Sem consumidores; o módulo pode ser eliminado se retirados também seus imports. Isso não inclui os modelos ETL. |
| `core/tables.py:185` | `OfficeMembershipOfficeTable` | Sem referências; não remover `OfficeMembership` nem as outras tabelas de membros. |
| `task/forms.py:310` | `TaskSurveyAnswerForm` | Sem uso. `TaskSurveyAnswer` continua sendo criado e consultado diretamente por views e modelos. |
| `task/models.py:112,163` | `TypeTaskTypes`, `SurveyType` | São enums sem consumidores, inclusive nas migrations pesquisadas. Não são modelos Django; a retirada dessas definições não elimina tabelas. Preservar `TaskStatus` e `CheckPointType`. |
| `manager/utils.py:51` | `get_template_value_values` | Sem chamadas. Preservar `get_template_value_value` (singular), que está em uso. |
| `survey/models.py:28` | `get_legacy_type_map` | Sem chamadas. `LEGACY_TYPES` e `LegacySurveyType` formam uma dependência adicional aparentemente exclusiva desse helper; não foram retirados na simulação e devem ser incluídos em uma validação complementar caso também sejam eliminados. |

## CodeMirror

`dashboard/static/codemirror` contém 323 arquivos, com 2.772.149 bytes no total (aproximadamente 2,64 MiB). Todos os caminhos existem também em `core/static/codemirror`.

- 129 arquivos são idênticos byte a byte.
- 194 são diferentes: não se trata de duas cópias integralmente idênticas.
- Para todos os 323 caminhos, os finders da configuração em execução escolhem `core/static/codemirror`.
- O widget ativo `CodeMirrorTextarea`, em `core/widgets.py`, usa o prefixo `codemirror/`; os arquivos de biblioteca, modo Python e tema material resolvem para core.

Recomendação: retirar a árvore de dashboard, preservando a de core. A justificativa é a precedência efetivamente verificada, não apenas a igualdade de conteúdo. Antes de publicar a limpeza, executar `collectstatic` no ambiente de validação e verificar os editores no admin/formulários. Esta análise não comparou o conteúdo já coletado no volume servido pelo nginx.

## Manter fora da primeira limpeza

| Candidato | Motivo |
|---|---|
| `core/tasks.py:35` — `delete_imported_xls` | Sem chamadores no repositório ou nomes no banco pesquisado, mas registrada como tarefa Celery. Não foram inspecionadas filas, tarefas reservadas/agendadas no worker ou produtores externos. Confirmar esses pontos antes de remover o nome registrado. As tarefas específicas de limpeza de cidades e tabela de preços têm chamadas ativas. |
| Modelos e app `etl` | `DashboardETL` continua registrado no admin e a limpeza `etl.tasks.remove_old_etldashboard` permanece agendada diariamente às 02h na configuração local. As três tabelas consultadas estão vazias localmente; isso não prova ausência de dados em outros ambientes. Eliminar modelos exigiria decidir o destino dos dados, retirar registros/configuração e criar migrations. |
| Modelos e app `billing` | Há rotas ativas de dados de cobrança e referências de OS aos modelos. A remoção da integração Gerencianet não tornou o app inteiro morto. |
| `core.models.ContactUs` | A retirada de `ContactForm` não inclui esse modelo. Ele tem teste próprio e existência persistente via migrations; eventual descontinuação é uma mudança de esquema separada. |
| `task.models.TaskSurveyAnswer` | Tem uso direto no registro, consulta e validação de respostas. Somente o formulário listado está sem uso. |
| `LegacyCode`, templates e bibliotecas compartilhados | Nomes legados ou baixa conectividade no grafo não bastam: há herança, referências por strings e convenções do framework. Não fazem parte da proposta de exclusão. |

## Validação necessária ao implementar

1. Remover as definições e somente os imports que ficarem sem uso; retirar conjuntamente `get_offices_to_pay` e `OfficeToPaySerializer`.
2. Rodar os checks reais e `makemigrations --check --dry-run`; a primeira limpeza não deve alterar o esquema.
3. Exercitar criação/edição de pastas, usuários, upload de anexos, questionários, contas a pagar e notificações. A simulação de imports/checks não executou esses fluxos nem a suíte de testes.
4. Validar a coleta de estáticos e os editores CodeMirror antes de publicar a remoção da cópia.
5. Atualizar o grafo com `graphify update .` após modificar código.

As conclusões sobre configuração e dados valem para o ambiente local inspecionado nesta data. Não houve inspeção de produção, de consumidores externos nem de código montado dinamicamente sem os nomes literais pesquisados. A análise sustenta uma limpeza de baixo risco, sem prometer cobertura de execução completa.

Etapa posterior: a [suíte de regressão e sua referência](TESTES.md) foi preparada antes de implementar qualquer exclusão. Ela registra também os defeitos encontrados no comportamento atual da aplicação.
