#!/usr/bin/env bash
# Setup AKPlanning
# execute as Utils/check.sh

# abort on error, print executed commands
set -ex

# remove old virtualenv
rm -rf env/

# Setup Python Environment
# Requires: Virtualenv, appropriate Python installation
virtualenv env -p python3.7
source env/bin/activate
pip install --upgrade setuptools pip wheel
pip install -r requirements.txt

# Setup database
python manage.py migrate

# Create superuser
# Credentials are entered interactively on CLI
python manage.py createsuperuser

deactivate
