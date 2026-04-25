#!/usr/bin/env bash
# exit on error
set -o errexit

# Dispatches background tasks
python manage.py qcluster &

# Starts production web server
gunicorn payout_engine.wsgi:application --bind 0.0.0.0:$PORT
