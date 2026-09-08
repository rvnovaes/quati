"""
Configuração do pytest.

Os signals de criação de escritório dependem das configurações-modelo da app manager
(fixture 'template') e dos tipos de serviço principais (fixture 'type_task_main').
Carregamos essas fixtures uma vez no banco de testes.
"""
import pytest
from django.core.management import call_command


@pytest.fixture(scope='session')
def django_db_setup(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        call_command('loaddata', 'auth_user', 'template', 'type_task_main', 'email_template', verbosity=0)
