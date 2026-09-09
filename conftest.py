"""
Configuração do pytest.

Os signals de criação de escritório dependem das configurações-modelo da app manager
(fixture 'template') e dos tipos de serviço principais (fixture 'type_task_main').
Carregamos essas fixtures uma vez no banco de testes.
"""
import pytest
from django.core.management import call_command
from django.db import connection


@pytest.fixture(scope='session')
def django_db_setup(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        # Production installs this extension through the PostgreSQL init script;
        # pytest creates a separate database, so it needs the same prerequisite.
        with connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
        call_command('loaddata', 'auth_user', 'template', 'type_task_main', 'email_template', verbosity=0)


@pytest.fixture(autouse=True)
def isolated_runtime(settings, tmp_path):
    """Never write uploads into the development media volume."""
    from django.core.cache import cache
    settings.MEDIA_ROOT = str(tmp_path / "media")
    cache.clear()
    yield
    cache.clear()
