# Modernização do EZL (setembro de 2026)

Branch: `feature/modernizacao`, a partir de `producao` (último commit de setembro de 2019).

## Versões

| Componente | Antes | Depois |
|---|---|---|
| Python | 3.6 | 3.12 |
| Django | 1.11 | 5.2 LTS |
| Celery | 4.2 + librabbitmq + eventlet | 5.x (prefork) |
| Channels | 1.1.8 + asgi-redis + daphne 1.3 | 4.x + channels-redis + daphne 4 |
| PostgreSQL | 9.6 | 16 |
| Redis / RabbitMQ / nginx | 4.0 / 3 / 1.13 | 7 / 3 / 1.27 |
| Servidor WSGI | uWSGI | gunicorn |
| Driver PostgreSQL | psycopg2 2.7 | psycopg 3 |

Bibliotecas removidas: django-material, django-codemirror-widget, django-file-form, jsonfield2, django-rest-auth (→ dj-rest-auth), rest-condition, django-dbconn-retry, raven, django-storages/boto3, sendgrid, gerencianet, luigi, SQLAlchemy, pymssql, paramiko, sshtunnel, retrying, model-mommy (→ model-bakery).

## Integrações removidas

- **Advwin** (SQL Server legado): apps `advwin_models` e `connections`, ETL Luigi (`etl/advwin_ezl`, `etl/ezl_advwin`, `etl/celery`), container `luigi`, signals de exportação de OS/ECM/histórico em `task/signals.py`, management commands `run_etl_suit`, `reexport_task_advwin`, `reexport_ecm_folder`, `remove_duplicate_ecm`. Os campos `legacy_code`/`system_prefix` e o mixin `LegacyCode` foram mantidos.
- **Gerencianet** (pagamento por cartão): `billing/gerencianet_api`, views de cobrança, JS/lightbox e modal de checkout. Models de `billing` (Plan, PlanOffice, Charge, ChargeItem, BillingDetails) mantidos. Preços com cobrança pré-paga exibem aviso de indisponibilidade até um novo sistema de boletos ser implantado.
- **Servidor Windows / CIFS / SFTP**: mounts `/mnt/windows_ecm`, `deploy/` (fabfile, chaves), `scripts/` (backup S3).
- **Amazon S3**: storage passa a ser `FileSystemStorage` no volume `web-media`.
- **SendGrid**: envio via SMTP (Postfix). Os 7 templates dinâmicos foram recriados como templates Django em `task/templates/mail/` e `core/templates/mail/sign_up.html`.
- **Sentry (raven), Datadog, Traefik, certbot, pgweb**: removidos do compose.
- **Dump de produção** em `containers/db/docker-entrypoint-initdb.d/` (dados pessoais reais) e `pg_hba.conf` com `trust` para qualquer IP: removidos.

## Configuração

`config/*.ini` foi substituído por variáveis de ambiente lidas em `ezl/settings.py` (ver `.env.example`). As credenciais que estavam comitadas (SendGrid, AWS, Zoho, SQL Server, chave de deploy) devem ser consideradas comprometidas e revogadas.

## Migrations

O histórico de 494 migrations foi regenerado do zero (uma `0001_initial` por app, mais `task/0002_database_views` com as views SQL `dashboard_view` e `task_filter_view`). Motivo: a decisão de partir de banco novo, somada a 49 data migrations que importavam models reais e o Advwin, tornava a cadeia antiga inexecutável. Bancos antigos **não** podem ser migrados diretamente; seria preciso um dump/restore com `--fake-initial` e ajustes manuais.

Fixtures carregadas pelo `make load_fixtures0`: `auth_user`, `template`, `country`, `state`, `court_district`, `email_template`, `type_task_main`, `card`, `line_chart`, `doughnut_chart`, `bar_chart`, além de `ezl_create_groups_and_permissions`.

## Ajustes de código relevantes

- `url()` → `re_path`, `urlresolvers` → `django.urls`, `staticfiles` → `static`, `on_delete` explícito (PROTECT) em 30 FKs, `JSONField` nativo, `ugettext` → `gettext`, `assignment_tag` → `simple_tag`, `is_authenticated` como propriedade, DRF `set_context` → `requires_context`, `base_name` → `basename`, django-filter `name=` → `field_name=`.
- Tag `{% querystring %}` do django-tables2 (removida na v3) reimplementada em `core/templatetags/ezl_tables.py`.
- Formulários: layout do django-material substituído por `core/templates/core/includes/form_rows.html`; widget `CodeMirrorTextarea` próprio em `core/widgets.py`; upload múltiplo nativo (`MultipleFileField`).
- Chat: `chat/consumers.py` reescrito como `AsyncWebsocketConsumer`; `ezl/asgi.py` com `ProtocolTypeRouter`.
- Views de exclusão em lote (`MultiDeleteView`, `LawSuitDeleteView`) ganharam `post()` (Django 4+ exige pk no `post` padrão).
- Signals de `core` e `task` agora são registrados em `AppConfig.ready()` (antes dependiam de import colateral em views).
- `filter_valid_choice_form` não consulta mais o banco no import dos forms.

## Testes

`pytest` com `conftest.py` carregando as fixtures base. Os testes de 2019 estavam desatualizados em relação ao código: 45 passam, 23 falham por cenários incompletos dos próprios testes (escritório ausente na sessão, pasta padrão inexistente, formulários com campos novos obrigatórios). Precisam ser reescritos.
