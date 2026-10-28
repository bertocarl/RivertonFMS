#!/bin/sh
# Local setup with SQLite. Run from the project folder: sh scripts/setup.sh
set -e
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
python manage.py makemigrations accounts forecourt shifts sales purchases ledger reports
python manage.py migrate
python manage.py seed_bonje "$@"
echo ""
echo "Next: python manage.py createsuperuser   (or re-run this script with --demo for sample users)"
echo "Then: python manage.py runserver"
