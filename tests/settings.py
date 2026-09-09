"""Isolated infrastructure for tests; application behavior stays unchanged."""
import os
import tempfile

os.environ["LOG_DIR"] = os.path.join(tempfile.gettempdir(), "ezl-tests-logs")
from ezl.settings import *  # noqa: F403,E402

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
DEFAULT_TO_EMAIL = None
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
