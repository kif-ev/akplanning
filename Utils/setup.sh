#!/usr/bin/env bash
# Setup AKPlanning
# execute as Utils/setup.sh

# abort on error, print executed commands
set -ex

# remove old virtualenv
rm -rf venv/

# Setup Python Environment
# Requires: Virtualenv, appropriate Python installation
virtualenv venv -p python3.9
source venv/bin/activate
pip install --upgrade setuptools pip wheel
pip install -r requirements.txt

# set environment variable when we want to update in production
if [ "$1" = "--prod" ]; then
    export DJANGO_SETTINGS_MODULE=AKPlanning.settings_production
fi
if [ "$1" = "--ci" ]; then
    export DJANGO_SETTINGS_MODULE=AKPlanning.settings_ci
fi

# Setup database
python manage.py migrate

# Prepare static files and translations
python manage.py collectstatic --noinput
python manage.py compilemessages -l de_DE

# Create superuser
# Credentials are entered interactively on CLI
python manage.py createsuperuser

# Generate documentation (but not for CI use)
if [ -n "$1" = "--ci" ]; then
    cd docs
    make html
    cd ..
fi


deactivate
