#!/usr/bin/env bash
# Setup AKPlanning
# execute as ./Utils/setup.sh [--prod OR --ci]

# abort on error, print executed commands
set -ex

# Setup Python Environment
# remove old virtualenv
rm -rf venv/

# Requires: Virtualenv, appropriate Python installation
virtualenv venv -p python3.13
source venv/bin/activate
pip install --upgrade setuptools pip wheel

if [ "$1" = "--ci" ]; then
  # Everything needed by any CI job (tests, linting, documentation), so the jobs can share the cached virtualenv
  pip install -r requirements.txt -r requirements/mysql.txt -r requirements/lint.txt
  export DJANGO_SETTINGS_MODULE=AKPlanning.settings_ci
else
  pip install -r requirements.txt
fi

# set environment variable when we want to setup in production
if [ "$1" = "--prod" ]; then
  pip install -r requirements/mysql.txt
  export DJANGO_SETTINGS_MODULE=AKPlanning.settings_production
fi

# Setup database and static files (but not for CI use, every job sets up what it needs itself)
if [ "$1" != "--ci" ]; then
    python manage.py migrate
    python manage.py collectstatic --noinput
fi

# Prepare translations
python manage.py compilemessages -l de_DE --ignore venv --ignore .cache

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
