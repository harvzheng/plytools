"""Shared pytest config. Adds scripts/ to sys.path so tests can import scripts as modules."""
import pathlib
import sys

SCRIPTS_DIR = pathlib.Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
