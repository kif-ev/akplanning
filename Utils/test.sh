#!/usr/bin/env bash
# Test the AKPlanning setup
# execute as Utils/test.sh

# activate virtualenv when necessary
if [ -z ${VIRTUAL_ENV+x} ]; then
    source venv/bin/activate
fi

# enable really all warnings, some of them are silenced by default
if [[ "$@" == *"--all"* ]]; then
    export PYTHONWARNINGS=all
fi

# in case of testing production setup
if [[ "$@" == *"--prod"* ]]; then
    export DJANGO_SETTINGS_MODULE=AKPlanning.settings_production
    ./manage.py test --deploy
fi

./manage.py test
