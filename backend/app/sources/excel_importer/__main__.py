"""Точка входа: python -m app.sources.excel_importer (см. cli.py)."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
