# noinspection PyUnresolvedReferences
from AKPlanning.settings import *

DEBUG = False
SECRET_KEY = '+7#&=$grg7^x62m#3cuv)k$)tqx!xkj_o&y9sm)@@sgj7_7-!+'

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'HOST': 'mysql',
        'NAME': 'test',
        'USER': 'django',
        'PASSWORD': 'mysql',
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'"
        },
        'TEST': {
            'NAME': 'test',
        },
    }
}
