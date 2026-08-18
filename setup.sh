#!/bin/bash

# Install dependencies
pip install setuptools
pip install -r requirements.txt

# Static files are served directly from STATIC_ROOT = static/
# No collectstatic needed since source and root are consolidated.
echo "Static files consolidated in static/ directory"
