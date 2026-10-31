import os

NOTES_DIR = os.path.join(os.path.dirname(__file__), "notes")


def read_note(name):
    # VULN: path traversal ("../../etc/passwd" escapes NOTES_DIR)
    with open(os.path.join(NOTES_DIR, name)) as f:
        return f.read()
