import os
import requests

if os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

grok_key = os.environ.get("GROK_API_KEY", "")

headers = {
    'Authorization': f'Bearer {grok_key}'
}

r = requests.get('https://api.x.ai/v1/models', headers=headers)
print(r.status_code)
print(r.text)
