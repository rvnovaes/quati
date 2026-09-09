# Retirada das regras de importação legada

## Decisão

Não haverá novas importações de dados antigos. O funcionamento normal da aplicação não deve depender de registros fictícios produzidos por essas importações. Essa decisão não implica apagar dados históricos nem desativar a importação operacional de planilhas.

## Limpeza realizada

- A edição de pastas usa a consulta normal do Django, sem buscar um registro com `legacy_code='REGISTRO-INVÁLIDO'`. Isso corrige o BUG-001 na abertura e no salvamento.
- Foram removidos os helpers `get_invalid_data`, `remove_invalid_registry` e `filter_valid_choice_form`, com todos os seus consumidores em Python.
- Listagens e pesquisa genérica não fazem consultas adicionais para localizar e ocultar registros fictícios.
- Os querysets das APIs de pastas, processos, instâncias e pessoas preservam os filtros existentes de escritório, sem excluir registros pelo marcador legado.
- Formulários, filtros e autocompletes de core, processos, OS, financeiro e anexos usam seus querysets diretamente. Filtros existentes de atividade, escritório, papel e relacionamento foram preservados.
- Foram removidos overrides de listagem que apenas encaminhavam a chamada ao pai para aplicar o decorator legado.

Se ainda existir um registro com o antigo nome ou código especial, ele passa a ser tratado como dado comum. Nenhum registro foi excluído ou alterado no banco por esta limpeza. A validade de uma opção depende dos filtros normais de cada tela, e não de uma convenção de nomes da antiga importação.

## Componentes preservados e motivo

| Componente | Motivo |
|---|---|
| `LegacyCode.legacy_code` e `system_prefix` | Armazenam referências existentes; são utilizados em serializers, consultas, filtros e relatórios. Remover colunas exige uma migração de dados e revisão desses contratos. |
| `task/task_import.py`, resources e loaders de planilhas | A aplicação ainda expõe importações operacionais de OS e preços. Encerrar importações de sistemas antigos não encerra esses fluxos. |
| Models de `etl` e status/inconsistências relacionados | Permanecem referenciados pelo dashboard e pelas consultas de OS, além de conterem histórico. |
| Limpeza periódica de logs de ETL | É uma tarefa de retenção de histórico, não uma nova importação. |
| Proteções de exclusão de `Ecm` e `EcmTask` | Preservam anexos existentes, inclusive compartilhados, cópias e referências externas. Encerrar futuras importações não comprova que esses vínculos deixaram de existir. |
| Migrations anteriores | Necessárias para reconstruir o banco e manter o histórico do esquema. |
| Fixtures históricas `person.xml`, `instance.xml`, `court_division.xml` e `type_movement.xml` | Ainda contêm registros fictícios, mas não são carregadas pelo seed atual (`scripts/seed_db.sh`) nem pela suíte. Foram preservadas como dados históricos; não devem ser usadas para inicializar a aplicação atual. |

Esses componentes não foram classificados como código morto apenas pelo nome “legado”. Uma futura remoção deve identificar consumidores restantes e tratar os dados existentes antes de eliminar campos, integrações ou proteções.

## Validação

Os cenários de regressão estão em `tests/test_legacy_rule_cleanup.py` e no teste de edição de pasta de `lawsuit/tests.py`. Resultados da suíte e limitações estão em `docs/TESTES.md`.
