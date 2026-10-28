#!/bin/sh
# Web container: prepare the database, then start. Worker container: just start.
set -e
if [ "$1" = "gunicorn" ]; then
  python manage.py makemigrations --noinput accounts forecourt shifts sales purchases ledger reports
  python manage.py migrate --noinput
  python manage.py seed_bonje
  python manage.py collectstatic --noinput
fi
exec "$@"
