#!/bin/sh

function wait_for_db()
{
  while ! ./manage.py sqlflush > /dev/null 2>&1 ;do
    echo "Waiting for the db to be ready."
    sleep 1
  done
}

if [ "$SECRET_KEY" == "" ] ;then
  echo "Need the environment variable SECRET_KEY."
  exit 1
fi

echo "SECRET_KEY = '$SECRET_KEY'" >> ./AKPlanning/settings_secrets.py
echo "HOSTS = $HOSTS" >> ./AKPlanning/settings_secrets.py
echo "DB_NAME = '$DB_NAME'" >> ./AKPlanning/settings_secrets.py
echo "DB_USER = '$DB_USER'" >> ./AKPlanning/settings_secrets.py
echo "DB_PASSWORD = '$DB_PASSWORD'" >> ./AKPlanning/settings_secrets.py
echo "DB_HOST = '$DB_HOST'" >> ./AKPlanning/settings_secrets.py

if [ "$AUTO_MIGRATE_DB" == "true" ] ;then
  wait_for_db
  echo "Applying DB migrations"
  ./manage.py migrate
fi

if [ "$DJANGO_SUPERUSER_PASSWORD" != "" ] ;then
  wait_for_db
  echo "Trying to create superuser."
  ./manage.py createsuperuser --noinput
fi

./manage.py collectstatic --noinput
./manage.py compilemessages -l de_DE
uwsgi --ini .docker/uwsgi.ini
