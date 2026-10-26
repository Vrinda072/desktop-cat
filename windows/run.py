"""Starts Desktop Cat: `python windows/run.py` (and PyInstaller's entry point)."""
import sys

from desktop_cat.app import main

if __name__ == "__main__":
    sys.exit(main())
