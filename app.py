import os
from flask import Flask, render_template, request, redirect, session
from pymongo import MongoClient
import requests
import base64
import io
import uuid
import random
import smtplib
import ssl
from datetime import datetime
try:
    from twilio.rest import Client as TwilioClient
except ImportError:
    TwilioClient = None

# Load .env manually to avoid python-dotenv dependency issues
if os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

app = Flask(__name__)
app.secret_key = "buddy_ai_secret"

# ---------------- DATABASE ----------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)
db = client['buddy_ai']
users_collection = db['users']
questions_collection = db['questions']

# Email Config
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_USER = os.getenv("SMTP_USER") # Your Gmail
SMTP_PASS = os.getenv("SMTP_PASS") # Gmail App Password

# Twilio Config (SMS)
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE = os.getenv("TWILIO_PHONE_NUMBER")

def send_verification_email(receiver_email, code):
    if not SMTP_USER or not SMTP_PASS:
        print(f"\n[MOCK MAIL] Verification code for {receiver_email}: {code}\n")
        return True
    
    subject = "Verify your Buddy AI Account"
    body = f"Your 6-digit verification code is: {code}\nKeep this code private."
    message = f"Subject: {subject}\n\n{body}"
    
    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, receiver_email, message)
        return True
    except Exception as e:
        print(f"SMTP Error: {e}")
        return False

def send_sms_verification(phone_number, code):
    if not TWILIO_SID or not TWILIO_TOKEN or not TWILIO_PHONE or not TwilioClient:
        print(f"\n[MOCK SMS] Verification code for {phone_number}: {code}\n")
        return True
    
    try:
        client = TwilioClient(TWILIO_SID, TWILIO_TOKEN)
        client.messages.create(
            body=f"Your Buddy AI verification code is: {code}",
            from_=TWILIO_PHONE,
            to=phone_number
        )
        return True
    except Exception as e:
        print(f"Twilio Error: {e}")
        return False

# ---------------- AUTH ROUTES ----------------

@app.route("/")
def home():
    if "user" in session:
        return redirect("/dashboard")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        phone = request.form.get("phone")
        password = request.form.get("password")

        if users_collection.find_one({"username": username}):
            return render_template("register.html", error="Username already exists!")

        code = str(random.randint(100000, 999999))
        users_collection.insert_one({
            "username": username,
            "email": email,
            "phone": phone,
            "password": password,
            "is_verified": False,
            "verification_code": code
        })
        
        # Send code to both Email and Phone
        mail_sent = send_verification_email(email, code)
        sms_sent = send_sms_verification(phone, code)
        
        if mail_sent or sms_sent:
            session["unverified_user"] = username
            return redirect("/verify")
        else:
            return render_template("register.html", error="Error sending code. Check configuration.")

    return render_template("register.html")

@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")

    user = users_collection.find_one({"username": username, "password": password})
    if user:
        if not user.get("is_verified", False):
            session["unverified_user"] = username
            return redirect("/verify")
        session["user"] = username
        return redirect("/dashboard")
    else:
        return render_template("login.html", error="Invalid username or password")

@app.route("/verify", methods=["GET", "POST"])
def verify():
    username = session.get("unverified_user")
    if not username:
        return redirect("/login")
        
    if request.method == "POST":
        code = request.form.get("code")
        user = users_collection.find_one({"username": username, "verification_code": code})
        
        if user:
            users_collection.update_one({"username": username}, {"$set": {"is_verified": True}})
            session.pop("unverified_user")
            session["user"] = username
            return redirect("/dashboard")
        else:
            return render_template("verify.html", error="Invalid verification code.")
            
    return render_template("verify.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/")

@app.route("/new_chat")
def new_chat():
    if "user" in session:
        session["chat_id"] = str(uuid.uuid4())
    return redirect("/dashboard")

# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
@app.route("/chat/<chat_id>")
def dashboard(chat_id=None):
    if "user" not in session:
        return redirect("/")
    
    # Track the current active chat
    if chat_id:
        session["chat_id"] = chat_id
    elif "chat_id" not in session:
        session["chat_id"] = str(uuid.uuid4())
    
    active_chat_id = session["chat_id"]

    # fetch unique conversations for the sidebar
    all_user_qs = list(questions_collection.find({"username": session["user"]}).sort("timestamp", -1))
    
    convo_map = {}
    for q in all_user_qs:
        cid = q.get("chat_id")
        if cid and cid not in convo_map:
            # Use first question of thread as name
            convo_map[cid] = (q["question"][:30] + "..") if len(q["question"]) > 30 else q["question"]
    
    conversations = [{"id": cid, "name": name} for cid, name in convo_map.items()]

    # fetch history for CURRENT conversation
    user_questions = list(questions_collection.find({
        "username": session["user"],
        "chat_id": active_chat_id
    }).sort("timestamp", 1))
    
    chat = []
    for q in user_questions:
        chat.append({"role": "user", "content": q["question"]})
        chat.append({
            "role": "assistant", 
            "content": f"{q.get('best', '')}"
        })

    if user_questions:
        last_q = user_questions[-1]
        return render_template("ai_dashboard.html", user=session["user"], chat=chat,
                               latest_gemini=last_q.get("ai1"),
                               latest_grok=last_q.get("ai2"),
                               latest_best=last_q.get("best"),
                               current_question=last_q.get("question"),
                               conversations=conversations,
                               active_chat_id=active_chat_id)
    else:
        return render_template("ai_dashboard.html", user=session["user"], chat=chat, 
                               conversations=conversations, active_chat_id=active_chat_id)

# ---------------- AI LOGIC ----------------

def ai_model_gemini(question, image_b64=None, mime_type="image/jpeg"):
    api_key = os.getenv("GEMINI_API_KEY")
    groq_key = os.getenv("GROK_API_KEY")
    
    # Try Gemini first
    if api_key and api_key != "your_gemini_api_key_here":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        
        # Multimodal parts
        parts = [{"text": question}]
        if image_b64:
            parts.append({
                "inline_data": {
                    "mime_type": mime_type,
                    "data": image_b64
                }
            })
            
        data = {"contents": [{"parts": parts}]}
        
        try:
            resp = requests.post(url, json=data, timeout=12)
            if resp.status_code == 200:
                return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            elif resp.status_code == 429:
                # Automatic fallback to 1.5-flash-8b if 2.0quota exceeded
                backup_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-8b:generateContent?key={api_key}"
                resp2 = requests.post(backup_url, json=data, timeout=12)
                if resp2.status_code == 200:
                    return resp2.json()["candidates"][0]["content"]["parts"][0]["text"]
                return "⚠️ Gemini quota exceeded. Please wait a minute or check your plan."
            else:
                return f"Gemini API Error ({resp.status_code})."
        except requests.exceptions.ConnectionError:
            return "⚠️ Gemini connection failed. Please check your network."
        except: pass

    # Fallback to Groq if Gemini is down/limited
    if groq_key and groq_key.startswith("gsk_"):
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {groq_key}"}
            
            # Groq fallback uses llama-3.2-11b-vision for image backup or 3.3-70b for text
            model = "llama-3.2-11b-vision-preview" if image_b64 else "llama-3.3-70b-versatile"
            
            content = [{"type": "text", "text": question}]
            if image_b64:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}
                })
                
            data = {
                "model": model,
                "messages": [{"role": "user", "content": content}]
            }
            resp = requests.post(url, headers=headers, json=data, timeout=12)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"] + "\n\n*(Note: Gemini quota exceeded, using Llama-3 Vision backup)*"
        except: pass

    return "⚠️ Gemini quota exceeded and no backup available. Please try again later."

def ai_model_grok(question, image_b64=None, mime_type="image/jpeg"):
    api_key = os.getenv("GROK_API_KEY")
    if not api_key or api_key == "your_grok_api_key_here":
        return "Grok/Groq API key not configured."
    
    # Detect if it's a Groq key (starts with gsk_) or an xAI Grok key
    is_groq = api_key.startswith("gsk_")
    
    if is_groq:
        url = "https://api.groq.com/openai/v1/chat/completions"
        # Corrected model names for Groq standard
        model = "llama-3.2-11b-vision-preview" if image_b64 else "llama-3.3-70b-versatile"
    else:
        url = "https://api.x.ai/v1/chat/completions"
        model = "grok-2-1212"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Multimodal content format for Groq/OpenAI
    if is_groq and image_b64:
        content = [
            {"type": "text", "text": question},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}}
        ]
    else:
        content = question

    data = {
        "messages": [
            {"role": "system", "content": "You are a helpful AI assistant."},
            {"role": "user", "content": content}
        ],
        "model": model,
        "temperature": 0.7
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=12)
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"]
        elif response.status_code == 401:
            return "⚠️ Invalid Grok/Groq API key."
        elif response.status_code == 429:
            return "⚠️ Grok/Groq quota exceeded. Please try again later."
        else:
            return f"{'Groq' if is_groq else 'Grok'} API Error ({response.status_code})."
    except requests.exceptions.ConnectionError:
        return f"⚠️ { 'Groq' if is_groq else 'Grok' } Connection failed (DNS Error). Please check your internet or flush DNS."
    except Exception as e:
        return f"Error connecting to {'Groq' if is_groq else 'Grok'} API: {str(e)}"

def compare_answers(ans1, ans2, question):
    # Fallback if one or both models returned an error
    err_keywords = ["API Error", "quota exceeded", "not configured", "Connection failed", "failed to resolve"]
    err1 = any(x.lower() in ans1.lower() for x in err_keywords)
    err2 = any(x.lower() in ans2.lower() for x in err_keywords)

    if err1 and err2:
        return f"System Alert: Both models are exhausted or unreachable.\n\nAI 1 (Gemini): {ans1}\n\nAI 2 (Groq): {ans2}"
    if err1: return ans2
    if err2: return ans1

    # LLM as a Judge
    gemini_key = os.getenv("GEMINI_API_KEY")
    groq_key = os.getenv("GROK_API_KEY")
    
    prompt = f"""You are an unbiased AI judge.
The user asked: "{question}"
Answer A: {ans1}
Answer B: {ans2}
Determine which one is better based on accuracy and helpfulness. Output ONLY the full winning answer text. Do not mention "Model A" or "Model B"."""

    # Try Gemini first
    if gemini_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
            data = {"contents": [{"parts": [{"text": prompt}]}]}
            resp = requests.post(url, json=data, timeout=10)
            if resp.status_code == 200:
                return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        except: pass

    # Fallback to Groq as Judge (if key is gsk_)
    if groq_key and groq_key.startswith("gsk_"):
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {groq_key}"}
            data = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}]
            }
            resp = requests.post(url, headers=headers, json=data, timeout=10)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
        except: pass

    # Final heuristic fallback
    return ans1 if len(ans1) >= len(ans2) else ans2

@app.route("/ask", methods=["POST"])
def ask():
    if "user" not in session:
        return redirect("/")

    question = request.form.get("question", "")
    file = request.files.get("file")
    
    image_b64 = None
    mime_type = "image/jpeg"

    if file and file.filename != "":
        # Process image
        mime_type = file.mimetype
        image_bytes = file.read()
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
    # If image provided with no text, give a default prompt
    if image_b64 and (not question or question.strip() == ""):
        question = "Please analyze and describe this image in detail."

    ai1 = ai_model_gemini(question, image_b64, mime_type)
    ai2 = ai_model_grok(question, image_b64, mime_type)
    best = compare_answers(ai1, ai2, question) # Judge still uses text for now

    # Save to MongoDB with chat_id
    questions_collection.insert_one({
        "username": session["user"],
        "chat_id": session.get("chat_id", str(uuid.uuid4())),
        "question": f"[IMAGE PROVIDED] {question}" if image_b64 else question,
        "ai1": ai1,
        "ai2": ai2,
        "best": best,
        "timestamp": datetime.now()
    })

    # Fetch updated questions for dashboard
    user_questions = list(questions_collection.find({"username": session["user"]}).sort("timestamp", 1))
    
    chat = []
    for q in user_questions:
        chat.append({"role": "user", "content": q["question"]})
        chat.append({
            "role": "assistant", 
            "content": f"{q.get('best', '')}"
        })

    # Render with the latest outputs included so the frontend can choose to display the comparison
    return render_template("ai_dashboard.html", user=session["user"], chat=chat, latest_gemini=ai1, latest_grok=ai2, latest_best=best, current_question=question)

@app.route("/export_chat")
def export_chat():
    if "user" not in session: return redirect("/")
    active_chat_id = session.get("chat_id")
    qs = list(questions_collection.find({"username": session["user"], "chat_id": active_chat_id}).sort("timestamp", 1))
    
    export_text = f"Buddy AI Conversation Export - {datetime.now()}\n" + "="*40 + "\n\n"
    for q in qs:
        export_text += f"USER: {q['question']}\n\nAI: {q['best']}\n\n" + "-"*20 + "\n\n"
    
    return export_text, 200, {'Content-Type': 'text/plain', 'Content-Disposition': 'attachment; filename=chat_export.txt'}

if __name__ == "__main__":
    app.run(debug=True)