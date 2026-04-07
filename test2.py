import os, json, requests
if os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, val = line.strip().split("=", 1)
                os.environ[key.strip()] = val.strip()

gk = os.environ.get("GEMINI_API_KEY", "")
r = requests.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={gk}").json()
gemini_models = [m["name"] for m in r.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]

xh = {"Authorization": "Bearer " + os.environ.get("GROK_API_KEY", "")}
r2 = requests.get("https://api.x.ai/v1/models", headers=xh).json()
grok_models = [m["id"] for m in r2.get("data", [])]

with open("models.json", "w", encoding="utf-8") as f:
    json.dump({"gemini": gemini_models, "grok": grok_models}, f, indent=2)
