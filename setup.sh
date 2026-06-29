#!/bin/bash

#install dependancies
pip install setuptools
pip install -r requirements.txt

# Run django Commands
python manage.py makemigrations
python manage.py 
python manage.py tailwind install
python manage.py collectstatic
python manage.py tailwind start