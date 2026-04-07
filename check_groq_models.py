import os
import requests

if os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

groq_key = os.environ.get("GROK_API_KEY", "")
r = requests.get('https://api.groq.com/openai/v1/models', headers={'Authorization': 'Bearer ' + groq_key})
print(r.text)
