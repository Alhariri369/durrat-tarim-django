#!/bin/bash
set -e

# Install dependencies
pip install setuptools
pip install -r requirements.txt

# Collect static files into STATIC_ROOT (staticfiles/) for WhiteNoise
python manage.py collectstatic --noinput
