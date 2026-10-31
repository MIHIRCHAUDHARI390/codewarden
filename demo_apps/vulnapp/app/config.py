import os

API_TOKEN = os.environ.get("API_TOKEN", "")


def auth_header():
    return {"Authorization": "Bearer " + API_TOKEN}
