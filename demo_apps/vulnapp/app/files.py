import os
from pathlib import Path

NOTES_DIR = os.path.join(os.path.dirname(__file__), "notes")


def read_note(name):
    base = Path(NOTES_DIR).resolve()
    target = (base / name).resolve()
    if not target.is_relative_to(base):
        raise ValueError("invalid note name: path escapes notes directory")
    with open(target) as f:
        return f.read()
