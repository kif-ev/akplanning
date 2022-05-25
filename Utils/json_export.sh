#!/usr/bin/env bash
# Update AKPlanning
# execute as Utils/update.sh id_to_export target_name_to_export_to [--prod]

# abort on error, print executed commands
set -ex

# activate virtualenv if necessary
if [ -z ${VIRTUAL_ENV+x} ]; then
    source venv/bin/activate
fi

# set environment variable when we want to update in production
if [ "$3" = "--prod" ]; then
    export DJANGO_SETTINGS_MODULE=AKPlanning.settings_production
fi

mkdir -p ../backups/
python manage.py dumpdata AKDashboard AKModel AKOnline AKPlan AKScheduling AKSubmission --indent=2 > "backups/akplanning_only.json" --traceback

python ./Utils/json_export.py $1 $2

rm backups/akplanning_only.json
