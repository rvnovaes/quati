"""
Configurações do Quati.

Todas as opções sensíveis ou dependentes de ambiente vêm de variáveis de ambiente
(ver .env.example). Os valores padrão servem apenas para desenvolvimento local.
"""
import datetime
import os
import subprocess
import tempfile
from decimal import ROUND_HALF_EVEN
from pathlib import Path

from celery.schedules import crontab
from django.urls import reverse_lazy

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def env_int(name, default):
    return int(os.environ.get(name, default))


def env_list(name, default=''):
    return [item.strip() for item in os.environ.get(name, default).split(',') if item.strip()]


def get_rev():
    """Revisão curta do git, usada como cache-buster dos arquivos estáticos."""
    try:
        return subprocess.check_output(
            ['git', 'rev-parse', '--short', 'HEAD'], stderr=subprocess.DEVNULL
        ).decode('utf-8').strip()
    except Exception:
        return env('EZL_REVISION', '')


# ---------------------------------------------------------------------------
# Ambiente
# ---------------------------------------------------------------------------
ENVIRONMENT = env('ENV', 'development')
DEBUG = env_bool('DEBUG', ENVIRONMENT == 'development')
SECRET_KEY = env('SECRET_KEY', 'dev-insecure-secret-key-change-me' if DEBUG else '')
if not SECRET_KEY:
    raise RuntimeError('Defina a variável de ambiente SECRET_KEY.')

REVIEW = get_rev()
MUST_LOGIN = True

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', '*')
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS', 'http://localhost:8000,http://localhost:8080')
CORS_ORIGIN_ALLOW_ALL = True
INTERNAL_IPS = env_list('INTERNAL_IPS', '127.0.0.1')

PROJECT_NAME = env('PROJECT_NAME', 'Quati')
PROJECT_LINK = env('PROJECT_LINK', 'http://localhost:8000')
WORKFLOW_URL_EMAIL = env('WORKFLOW_EMAIL', PROJECT_LINK)

# ---------------------------------------------------------------------------
# Apps / middleware
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.messages',
    'django.contrib.postgres',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.staticfiles',
    # Project apps
    'billing.apps.BillingConfig',
    'chat.apps.ChatConfig',
    'core.apps.CoreConfig',
    'dashboard.apps.DashboardConfig',
    'ecm.apps.EcmConfig',
    'etl.apps.EtlConfig',
    'financial.apps.FinancialConfig',
    'lawsuit.apps.LawsuitConfig',
    'manager.apps.ManagerConfig',
    'survey.apps.SurveyConfig',
    'task.apps.TaskConfig',
    # Third party
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'django_tables2',
    'django_filters',
    'bootstrap3',
    'django_extensions',
    'django_cleanup.apps.CleanupConfig',
    'dal',
    'dal_select2',
    'dal_queryset_sequence',
    'localflavor',
    'sequences.apps.SequencesConfig',
    'channels',
    'guardian',
    'djmoney',
    'rest_framework',
    'rest_framework.authtoken',
    'oauth2_provider',
    'import_export',
    'dj_rest_auth',
    'simple_history',
    'django_admin_json_editor',
    'corsheaders',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'simple_history.middleware.HistoryRequestMiddleware',
    'core.middleware.ReviewRequestMiddleware',
]

if DEBUG and env_bool('DEBUG_TOOLBAR', False):
    INSTALLED_APPS.append('debug_toolbar')
    MIDDLEWARE.insert(1, 'debug_toolbar.middleware.DebugToolbarMiddleware')

ROOT_URLCONF = 'ezl.urls'
SITE_ID = 1

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'templates',
            BASE_DIR / 'core/templates',
            BASE_DIR / 'core/templates/core/http_errors',
            BASE_DIR / 'ecm/templates',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.media',
            ],
        },
    },
]

WSGI_APPLICATION = 'ezl.wsgi.application'
ASGI_APPLICATION = 'ezl.asgi.application'

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# ---------------------------------------------------------------------------
# Banco de dados / cache / channels
# ---------------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('DB_NAME', 'ezl'),
        'USER': env('DB_USER', 'ezl'),
        'PASSWORD': env('DB_PASSWORD', 'ezl'),
        'HOST': env('DB_HOST', 'localhost'),
        'PORT': env('DB_PORT', '5432'),
        'CONN_MAX_AGE': env_int('DB_CONN_MAX_AGE', 60),
    }
}

REDIS_HOST = env('REDIS_HOST', 'localhost')
REDIS_PORT = env_int('REDIS_PORT', 6379)

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {'hosts': [(REDIS_HOST, REDIS_PORT)]},
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://{}:{}/1'.format(REDIS_HOST, REDIS_PORT),
        'OPTIONS': {'CLIENT_CLASS': 'django_redis.client.DefaultClient'},
    }
}

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env('CELERY_BROKER_URL', 'amqp://guest:guest@localhost:5672//')
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND', 'redis://{}:{}/2'.format(REDIS_HOST, REDIS_PORT))
CELERY_ENABLE_UTC = False
CELERY_TIMEZONE = env('TIME_ZONE', 'America/Sao_Paulo')
CELERY_TASK_ALWAYS_EAGER = env_bool('CELERY_TASK_ALWAYS_EAGER', False)
CELERY_TASK_IGNORE_RESULT = True
CELERY_SEND_TASK_EMAILS = False
CELERY_BEAT_SCHEDULE = {
    'task-remove_old_etldashboard': {
        'task': 'etl.tasks.remove_old_etldashboard',
        'schedule': crontab(minute=0, hour=env_int('BEAT_HOUR_DASHBOARD', 2)),
    },
    'task-clear_sessions': {
        'task': 'core.tasks.clear_sessions',
        'schedule': crontab(minute=0, hour=env_int('BEAT_HOUR_CLEAR_SESSIONS', 3)),
    },
}

# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------
if DEBUG:
    AUTH_PASSWORD_VALIDATORS = [
        {
            'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
            'OPTIONS': {'min_length': 1},
        },
    ]
else:
    AUTH_PASSWORD_VALIDATORS = [
        {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
        {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
        {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
        {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
    ]

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
    'guardian.backends.ObjectPermissionBackend',
)

LOGIN_REDIRECT_URL = reverse_lazy('inicial')

# django-allauth
SOCIALACCOUNT_ADAPTER = 'core.account.adapter.EzlSocialAccountAdapter'
ACCOUNT_LOGIN_METHODS = {'username'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']
SOCIALACCOUNT_QUERY_EMAIL = True
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
    }
}

# ---------------------------------------------------------------------------
# Internacionalização
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = env('TIME_ZONE', 'America/Sao_Paulo')
USE_I18N = True
USE_TZ = True

DATETIME_FORMAT = '%d/%m/%Y %H:%M'
DATETIME_INPUT_FORMATS = (DATETIME_FORMAT, )
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# django-money: moeda padrão BRL
CURRENCIES = ('BRL', )
DEFAULT_CURRENCY = 'BRL'
CURRENCY_DECIMAL_PLACES = 2
MONEY_ROUNDING = ROUND_HALF_EVEN

# ---------------------------------------------------------------------------
# Arquivos estáticos e de mídia
# ---------------------------------------------------------------------------
STATIC_URL = '/static/'
STATICFILES_DIRS = (BASE_DIR / 'static', )
STATIC_ROOT = env('STATIC_ROOT', str(BASE_DIR / 'staticfiles'))

MEDIA_URL = '/media/'
MEDIA_ROOT = env('MEDIA_ROOT', str(BASE_DIR / 'media'))

STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}

UPLOAD_DIRECTORY = 'uploads'

# ---------------------------------------------------------------------------
# E-mail (SMTP -> Postfix)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', 'localhost')
EMAIL_PORT = env_int('EMAIL_PORT', 25)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', False)
EMAIL_USE_SSL = env_bool('EMAIL_USE_SSL', False)
EMAIL_TIMEOUT = env_int('EMAIL_TIMEOUT', 30)
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', 'Quati <quati@labp2.direito.ufmg.br>')
SERVER_EMAIL = DEFAULT_FROM_EMAIL
# Quando definido, todo e-mail é redirecionado para este endereço (útil em homologação)
DEFAULT_TO_EMAIL = env('DEFAULT_TO_EMAIL') or None

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = env('LOG_DIR', os.path.join(tempfile.gettempdir(), 'ezl') if os.name == 'nt' else '/var/log/ezl')
os.makedirs(os.path.join(LOG_DIR, 'etl'), exist_ok=True)
LOG_FILE_TIMESTAMP = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '[%(asctime)s] %(levelname)s %(message)s',
            'datefmt': LOG_DATE_FORMAT,
        },
        'verbose': {
            'format': '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
            'datefmt': LOG_DATE_FORMAT,
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG' if DEBUG else 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'ezl_logfile': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'ezl.log'),
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'error_logfile': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'error.log'),
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console', 'error_logfile'],
    },
    'loggers': {
        'django': {'handlers': ['console', 'error_logfile'], 'level': 'INFO', 'propagate': False},
        'ezl': {'handlers': ['console', 'ezl_logfile'], 'level': 'INFO', 'propagate': False},
        'error_logger': {'handlers': ['console', 'error_logfile'], 'level': 'ERROR', 'propagate': False},
        'debug_logger': {'handlers': ['console'], 'level': 'DEBUG', 'propagate': False},
    },
}

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'oauth2_provider.contrib.rest_framework.OAuth2Authentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_FILTER_BACKENDS': ('django_filters.rest_framework.DjangoFilterBackend', ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': env_int('REST_PAGE_SIZE', 10),
}

OAUTH2_PROVIDER = {
    'OAUTH2_BACKEND_CLASS': 'oauth2_provider.oauth2_backends.JSONOAuthLibCore',
    'SCOPES': {
        'read': 'Read scope',
        'write': 'Write scope',
        'groups': 'Access to your groups',
    },
    'ACCESS_TOKEN_EXPIRE_SECONDS': env_int('REST_ACCESS_TOKEN_EXPIRE', 36000),
}
OAUTH2_PROVIDER_APPLICATION_MODEL = 'core.ExternalApplication'
