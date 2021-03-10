FROM python:3-alpine

RUN apk add --no-cache gcc python3-dev musl-dev libffi-dev mariadb-connector-c-dev gettext

ADD . /app
WORKDIR /app

RUN pip install -r requirements.txt -r .docker/extra_requirements.txt

ENV DJANGO_SETTINGS_MODULE=AKPlanning.settings_production

EXPOSE 3035
CMD ["sh", "/app/.docker/entrypoint.sh"]
