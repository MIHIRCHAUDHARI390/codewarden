# VULN: hardcoded secret (fake value, for the demo only)
API_TOKEN = "demo-4f9a8b7c6d5e4f3a2b1c"
def auth_header():
    return {"Authorization": "Bearer " + API_TOKEN}