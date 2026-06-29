#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
import dotenv

dotenv.load_dotenv()

def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "durrat_tarim.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
