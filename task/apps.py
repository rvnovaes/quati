from django.apps import AppConfig


class TaskConfig(AppConfig):
    name = 'task'

    def ready(self):
        from . import signals  # noqa: F401
