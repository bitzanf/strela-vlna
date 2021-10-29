"""
Django settings for soutez project.

Generated by 'django-admin startproject' using Django 3.1.3.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.1/ref/settings/
"""
import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

STRELA_VERZE = '1.6'

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '9p85p(rghc!n(&8^+5l_06p!36_6*-0%))k96agfi@bc7g+n_d'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
#DEBUG = False

ALLOWED_HOSTS = ['89.203.249.42']


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_extensions',
    'bootstrap4',
    'sequences.apps.SequencesConfig',
    'debug_toolbar',
    'latexify',
    'django_tex',
    'bootstrap_datepicker_plus',
    'selectable',
    'strela',
  
]

MIDDLEWARE = [
   # 'django.middleware.cache.UpdateCacheMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
   # 'django.middleware.cache.FetchFromCacheMiddleware',
]

ROOT_URLCONF = 'soutez.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'strela.context_processors.add_verze_context'
            ],
        },
    },
    {
        'NAME': 'tex',
        'BACKEND': 'django_tex.engine.TeXEngine', 
        'APP_DIRS': True,
    },
]

WSGI_APPLICATION = 'soutez.wsgi.application'
LATEX_INTERPRETER = 'lualatex'

# ulozeni session do Memcached
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'

# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases

DATABASES = {
#    'default': {
#        'ENGINE': 'django.db.backends.sqlite3',
#        'NAME': BASE_DIR / 'db.sqlite3',
#    }
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'strela_vlna',
        'USER': 'django',
        'PASSWORD': 'a5easfa4',
        'HOST': 'localhost',   # Or an IP Address that your DB is hosted on
        'PORT': '3306',
    }
}


# Password validation
# https://docs.djangoproject.com/en/3.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/3.1/topics/i18n/

#LANGUAGE_CODE = 'en-us'
LANGUAGE_CODE = 'cs'

#USE_TZ = True

#TIME_ZONE = 'UTC'
TIME_ZONE = 'Europe/Prague'

USE_I18N = True

USE_L10N = True




# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.1/howto/static-files/

STATIC_URL = '/static/'
#STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
#VENV_PATH = os.path.dirname(BASE_DIR)
STATIC_ROOT = os.path.join(BASE_DIR, "static")

INTERNAL_IPS = [
    '193.165.96.249',
    '127.0.0.1',
    '195.113.62.220',
    '90.179.35.68',
    '193.165.97.240'
]

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
        'LOCATION': '127.0.0.1:11211',
    }
}

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'strela.backends.TymBackend',
]

SHELL_PLUS_PRE_IMPORTS = (
    ('django.utils.timezone',('now')),
)    

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '%(levelname)s %(message)s',
        },
        'verbose': {
            'format': '%(levelname)s %(asctime)s '
                '%(name)s.%(funcName)s:%(lineno)s %(process)d %(thread)d '
                '%(message)s',
        },
        'request': {
            'format': '%(remote_addr)s %(username)s "%(request_method)s '
                '%(path_info)s %(server_protocol)s" %(http_user_agent)s '
                '%(message)s %(asctime)s',
        },
    },
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'formatter': 'verbose',
            'filename':  BASE_DIR / 'soutez.log',
        },
    },
    'loggers': {
        'django.request': {
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'strela': {
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}
DEFAULT_FROM_EMAIL = "petrgchd523@seznam.cz"
EMAIL_HOST = 'smtp.seznam.cz'
EMAIL_PORT = 587
EMAIL_HOST_USER = 'petrgchd523@seznam.cz'
EMAIL_HOST_PASSWORD = 'Streda03'
EMAIL_USE_TLS = True
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'