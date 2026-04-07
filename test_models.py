import os
import requests
from dotenv import load_dotenv

if os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, val = line.strip().split("=", 1)
                os.environ[key.strip()] = val.strip()

gemini_key = os.environ.get("GEMINI_API_KEY", "")
grok_key = os.environ.get("GROK_API_KEY", "")

# Gemini models
r = requests.get(f'https://generativelanguage.googleapis.com/v1beta/models?key={gemini_key}')
data = r.json()
print("GEMINI MODELS:")
if "models" in data:
    for m in data["models"]:
        if "generateContent" in m.get("supportedGenerationMethods", []):
            print(m["name"])
else:
    print(data)

# Grok models
r2 = requests.get('https://api.x.ai/v1/models', headers={'Authorization': 'Bearer ' + grok_key})
data2 = r2.json()
print("\nGROK MODELS:")
if "data" in data2:
    for m in data2["data"]:
        print(m["id"])
else:
    print(data2)
