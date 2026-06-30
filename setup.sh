#!/bin/bash

# Install dependencies
pip install setuptools
pip install -r requirements.txt

# Collect committed static assets for WhiteNoise/Vercel.
python manage.py collectstatic --noinput
