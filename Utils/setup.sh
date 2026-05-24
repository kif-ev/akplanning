#!/usr/bin/env bash
# Setup AKPlanning
# execute as ./Utils/setup.sh [--prod OR --ci]

# abort on error, print executed commands
set -ex

# Setup Python Environment
# remove old virtualenv if --ci flag is not set
if [ -z "$1" ] || [ "$1" != "--ci" ]; then
  rm -rf venv/
fi

# Requires: Virtualenv, appropriate Python installation
if [ ! -d "venv" ]; then
  virtualenv venv -p python3.13
fi
source venv/bin/activate
pip install --upgrade setuptools pip wheel

if [ "$1" = "--ci" ]; then
  pip install -r requirements/core.txt
  pip install -r requirements/mysql.txt
  export DJANGO_SETTINGS_MODULE=AKPlanning.settings_ci
else
  pip install -r requirements.txt
fi

# set environment variable when we want to setup in production
if [ "$1" = "--prod" ]; then
  pip install -r requirements/mysql.txt
  export DJANGO_SETTINGS_MODULE=AKPlanning.settings_production
fi

# Setup database
python manage.py migrate

# Prepare static files and translations
python manage.py collectstatic --noinput
python manage.py compilemessages -l de_DE

# Create superuser
# Credentials are entered interactively on CLI (but not for ci use)
if [ -z "$1" ] || [ "$1" != "--ci" ]; then
    python manage.py createsuperuser
fi
# Generate documentation (but not for CI use)
if [ -z "$1" ] || [ "$1" != "--ci" ]; then
    cd docs
    make html
    cd ..
fi

deactivate
