#!/usr/bin/env bash
# Update AKPlanning
# execute as ./Utils/update.sh

# abort on error, print executed commands
set -ex

# activate virtualenv if necessary
if [ -z ${VIRTUAL_ENV+x} ]; then
    source venv/bin/activate
fi

# set environment variable when we want to update in production
if [ "$1" = "--prod" ]; then
    export DJANGO_SETTINGS_MODULE=AKPlanning.settings_production
fi

# before potentially breaking anything, create a data backup
mkdir -p backups/
python manage.py dumpdata --indent 2 --natural-foreign --natural-primary -e contenttypes -e auth.Permission > "backups/$(date +"%Y%m%d%H%M")_datadump.json" --traceback

git pull
pip install --upgrade setuptools pip wheel
pip install --upgrade -r requirements.txt

./manage.py migrate
./manage.py collectstatic --noinput
./manage.py compilemessages -l de_DE


# Update documentation
cd docs
make html
cd ..

touch AKPlanning/wsgi.py
