import os
import requests

# Manual env load
if os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

groq_key = os.environ.get("GROK_API_KEY", "")
print(f"Key starts with: {groq_key[:4]}")

url = "https://api.groq.com/openai/v1/chat/completions"
headers = {"Authorization": f"Bearer {groq_key}"}
data = {
    "model": "mixtral-8x7b-32768",
    "messages": [{"role": "user", "content": "Hello"}]
}

try:
    resp = requests.post(url, headers=headers, json=data, timeout=10)
    print(f"Status: {resp.status_code}")
    print(resp.text[:200])
except Exception as e:
    print(f"Error: {e}")
