"""
Django settings for AKPlanning project.

Generated by 'django-admin startproject' using Django 2.2.6.

For more information on this file, see
https://docs.djangoproject.com/en/2.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/2.2/ref/settings/
"""

import os

from django.utils.translation import gettext_lazy as _
# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
from split_settings.tools import optional, include

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '+7#&=$grg7^x62m#3cuv)k$)tqx!xkj_o&y9sm)@@sgj7_7-!+'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = []

# Application definition

INSTALLED_APPS = [
    'AKModel.apps.AkmodelConfig',
    'AKDashboard.apps.AkdashboardConfig',
    'AKSubmission.apps.AksubmissionConfig',
    'AKScheduling.apps.AkschedulingConfig',
    'AKPlan.apps.AkplanConfig',
    'AKOnline.apps.AkonlineConfig',
    'AKModel.apps.AKAdminConfig',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'debug_toolbar',
    'bootstrap4',
    'fontawesome_5',
    'timezone_field',
    'rest_framework',
    'simple_history',
    'registration',
    'bootstrap_datepicker_plus',
    'django_tex',
]

MIDDLEWARE = [
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'csp.middleware.CSPMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'simple_history.middleware.HistoryRequestMiddleware',
]

ROOT_URLCONF = 'AKPlanning.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(BASE_DIR, 'templates'),
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
    {
        'NAME': 'tex',
        'BACKEND': 'django_tex.engine.TeXEngine',
        'APP_DIRS': True,
        'OPTIONS': {
            'environment': 'AKModel.environment.improved_tex_environment',
        },
    },
]

WSGI_APPLICATION = 'AKPlanning.wsgi.application'

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# Database
# https://docs.djangoproject.com/en/2.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

# Password validation
# https://docs.djangoproject.com/en/2.2/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/2.2/topics/i18n/

LANGUAGE_CODE = 'en-US'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

LANGUAGES = [
    ('de', _('German')),
    ('en', _('English')),
]

INTERNAL_IPS = ['127.0.0.1', '::1']

LATEX_INTERPRETER = 'lualatex'
LATEX_RUN_COUNT = 2

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.2/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')
STATICFILES_DIRS = (
    'static_common',
)

# Settings for Bootstrap
BOOTSTRAP4 = {
    # Use custom CSS
    "css_url": {
        "href": STATIC_URL + "common/css/bootstrap.css",
    },
    "javascript_url": {
        "url": STATIC_URL + "common/vendor/bootstrap/bootstrap-4.3.1.min.js",
    },
    "jquery_url": {
        "url": STATIC_URL + "common/vendor/jquery/jquery-3.3.1.min.js",
    },
    "jquery_slim_url": {
        "url": STATIC_URL + "common/vendor/jquery/jquery-3.3.1.slim.min.js",
    },
    "popper_url": {
        "url": STATIC_URL + "common/vendor/popper/popper-1.14.7.min.js",
    },
}

# Settings for FontAwesome
FONTAWESOME_5_CSS_URL = "//cdnjs.cloudflare.com/ajax/libs/font-awesome/5.11.2/css/all.css"
FONTAWESOME_5_PREFIX = "fa"

# Treat wishes as seperate category in submission views?
WISHES_AS_CATEGORY = True

FOOTER_INFO = {
    "repo_url": "https://gitlab.fachschaften.org/kif/akplanning",
    "impress_text": "",
    "impress_url": ""
}

# How many AKs should be visible as next AKs
PLAN_MAX_NEXT_AKS = 10
# Specify range of plan for screen/projector view
PLAN_WALL_HOURS_RETROSPECT = 3
# Should the plan use a hierarchy of buildings and rooms?
PLAN_SHOW_HIERARCHY = True
# For which time (in seconds) should changes of akslots be highlighted in plan?
PLAN_MAX_HIGHLIGHT_UPDATE_SECONDS = 2 * 60 * 60

# Show feed of recent changes in dashboard
DASHBOARD_SHOW_RECENT = True
# How many entries max?
DASHBOARD_RECENT_MAX = 25

# Registration/login behavior
SIMPLE_BACKEND_REDIRECT_URL = "/user/"
LOGIN_REDIRECT_URL = SIMPLE_BACKEND_REDIRECT_URL

# Content Security Policy
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'")
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'", "fonts.googleapis.com")
CSP_IMG_SRC = ("'self'", "data:")
CSP_FRAME_SRC = ("'self'", )
CSP_FONT_SRC = ("'self'", "data:", "fonts.gstatic.com")

# Emails
SEND_MAILS = True
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

include(optional("settings/*.py"))
