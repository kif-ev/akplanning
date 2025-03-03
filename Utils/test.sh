#!/usr/bin/env bash
# Test the AKPlanning setup
# execute as Utils/test.sh

# activate virtualenv when necessary
if [ -z ${VIRTUAL_ENV+x} ]; then
    source venv/bin/activate
fi

# enable really all warnings, some of them are silenced by default
for arg in "$@"; do
    if [[ "$arg" == "--all" ]]; then
        export PYTHONWARNINGS=all
    fi
done

# in case of checking production setup
for arg in "$@"; do
    if [[ "$arg" == "--prod" ]]; then
      export DJANGO_SETTINGS_MODULE=AKPlanning.settings_production
      ./manage.py test --deploy
    fi
done

# run tests
./manage.py test
