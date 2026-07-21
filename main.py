from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import Groq
import os, base64, bcrypt, jwt, uuid, httpx, random
from datetime import datetime, timedelta
from db import (init_db, save_message, get_history, delete_history,
    get_all_sessions, delete_messages_after, save_topic, get_all_topics,
    create_user, get_user_by_email, get_user_by_id, get_user_by_google_id,
    create_google_user, link_google_id_to_user, update_user_name,
    update_user_password, update_default_model, update_system_prompt,
    delete_all_history, save_shared_chat, get_shared_chat,
    verify_user_otp, update_otp, delete_unverified_user,
    get_pinned_sessions, toggle_pin)

load_dotenv()
app = FastAPI()
init_db()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "nova_ai_secret_key_2026")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "onboarding@resend.dev")
security = HTTPBearer()

def generate_otp():
    return str(random.randint(100000, 999999))

async def send_otp_email(to_email: str, name: str, otp: str):
    if not RESEND_API_KEY:
        print(f"[DEV] RESEND_API_KEY missing. OTP for {to_email}: {otp}")
        return
    async with httpx.AsyncClient() as c:
        res = await c.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": f"NOVA AI <{FROM_EMAIL}>",
                "to": [to_email],
                "subject": "Verify your NOVA AI account",
                "html": f"""
                    <div style="font-family:sans-serif;background:#14161C;color:#F4F4F5;padding:32px;border-radius:12px;">
                        <h2 style="color:#7C5CFF;">NOVA AI</h2>
                        <p>Hi {name},</p>
                        <p>Your verification code is:</p>
                        <div style="font-size:32px;font-weight:bold;letter-spacing:6px;color:#7C5CFF;margin:16px 0;">{otp}</div>
                        <p style="color:#9397A8;font-size:13px;">This code expires in 10 minutes.</p>
                    </div>
                """
            }
        )
        if res.status_code >= 300:
            print("Resend error:", res.status_code, res.text)

AVAILABLE_MODELS = {
    "llama-3.3-70b-versatile": "Llama 3.3 70B",
    "qwen/qwen3.6-27b": "Qwen 3.6 27B",
    "gemma2-9b-it": "Gemma 2 9B",
    "mixtral-8x7b-32768": "Mixtral 8x7B"
}

class ChatRequest(BaseModel):
    session_id: str
    message: str
    model: str = "llama-3.3-70b-versatile"

class TopicRequest(BaseModel):
    message: str

class SaveTopicRequest(BaseModel):
    session_id: str
    topic: str

class SignupRequest(BaseModel):
    name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class VerifyOtpRequest(BaseModel):
    email: str
    otp: str

class ResendOtpRequest(BaseModel):
    email: str

class UpdateNameRequest(BaseModel):
    name: str

class UpdatePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class UpdateModelRequest(BaseModel):
    model: str

class UpdateSystemPromptRequest(BaseModel):
    system_prompt: str

class ShareChatRequest(BaseModel):
    session_id: str

class PinRequest(BaseModel):
    session_id: str

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=["HS256"])
        return payload
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/", response_class=HTMLResponse)
def home(): return read_file("index.html")

@app.get("/login", response_class=HTMLResponse)
def login_page(): return read_file("login.html")

@app.get("/auth-success", response_class=HTMLResponse)
def auth_success(): return read_file("auth-success.html")

@app.get("/settings", response_class=HTMLResponse)
def settings_page(): return read_file("settings.html")

@app.get("/profile", response_class=HTMLResponse)
def profile_page(): return read_file("profile.html")

@app.get("/share/{share_id}", response_class=HTMLResponse)
def share_page(share_id: str): return read_file("share.html")

@app.get("/style.css")
def style(): return FileResponse("style.css", media_type="text/css")

@app.get("/script.js")
def script(): return FileResponse("script.js", media_type="application/javascript")

@app.post("/signup")
async def signup(request: SignupRequest):
    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    existing = get_user_by_email(request.email)
    if existing and existing.get("is_verified"):
        raise HTTPException(status_code=400, detail="Email already exists")
    if existing and not existing.get("is_verified"):
        delete_unverified_user(request.email)  # let them re-signup and get a fresh OTP

    hashed = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt()).decode()
    otp = generate_otp()
    expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
    user_id = create_user(request.name, request.email, hashed, otp, expires_at)
    if not user_id:
        raise HTTPException(status_code=400, detail="Email already exists")

    await send_otp_email(request.email, request.name, otp)
    return {"message": "OTP sent to your email", "email": request.email}

@app.post("/verify-otp")
def verify_otp(request: VerifyOtpRequest):
    user = get_user_by_email(request.email)
    if not user:
        raise HTTPException(status_code=404, detail="No account found for this email")
    if user.get("is_verified"):
        raise HTTPException(status_code=400, detail="Account already verified")
    if user.get("otp_expires_at") and datetime.utcnow() > datetime.fromisoformat(user["otp_expires_at"]):
        raise HTTPException(status_code=400, detail="OTP expired. Please request a new one.")
    if not verify_user_otp(request.email, request.otp):
        raise HTTPException(status_code=400, detail="Invalid OTP")
    token = jwt.encode({"id": user["id"], "name": user["name"], "email": user["email"]}, SECRET_KEY, algorithm="HS256")
    return {"token": token, "name": user["name"]}

@app.post("/resend-otp")
async def resend_otp(request: ResendOtpRequest):
    user = get_user_by_email(request.email)
    if not user:
        raise HTTPException(status_code=404, detail="No account found for this email")
    if user.get("is_verified"):
        raise HTTPException(status_code=400, detail="Account already verified")
    otp = generate_otp()
    expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
    update_otp(request.email, otp, expires_at)
    await send_otp_email(request.email, user["name"], otp)
    return {"message": "OTP resent"}

@app.post("/login")
def login(request: LoginRequest):
    user = get_user_by_email(request.email)
    if not user or not user.get("password"):
        raise HTTPException(status_code=401, detail="This email is registered via Google. Please use 'Continue with Google' to sign in.")
    if not bcrypt.checkpw(request.password.encode(), user["password"].encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("is_verified"):
        raise HTTPException(status_code=403, detail="Please verify your email before logging in")
    token = jwt.encode({"id": user["id"], "name": user["name"], "email": user["email"]}, SECRET_KEY, algorithm="HS256")
    return {"token": token, "name": user["name"]}

@app.get("/auth/google/login")
def google_login():
    redirect_uri = f"{APP_BASE_URL}/auth/google/callback"
    return RedirectResponse(
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=openid%20email%20profile"
        f"&access_type=offline"
    )

@app.get("/auth/google/callback")
async def google_callback(code: str):
    redirect_uri = f"{APP_BASE_URL}/auth/google/callback"
    async with httpx.AsyncClient() as c:
        token_res = await c.post("https://oauth2.googleapis.com/token", data={
            "code": code, "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri, "grant_type": "authorization_code"
        })
        access_token = token_res.json().get("access_token")
        user_info = (await c.get("https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"})).json()

    email = user_info.get("email")
    name = user_info.get("name", email)
    google_id = user_info.get("id")

    user = get_user_by_google_id(google_id)
    if not user:
        user = get_user_by_email(email)
        if user:
            link_google_id_to_user(user["id"], google_id)
        else:
            user_id = create_google_user(name, email, google_id)
            user = {"id": user_id, "name": name, "email": email}

    token = jwt.encode({"id": user["id"], "name": user["name"], "email": user["email"]}, SECRET_KEY, algorithm="HS256")
    return RedirectResponse(url=f"/auth-success?token={token}&name={name}")

@app.get("/api/me")
def me(user=Depends(get_current_user)):
    u = get_user_by_id(user["id"])
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": u["id"], "name": u["name"], "email": u["email"],
        "default_model": u.get("default_model", "llama-3.3-70b-versatile"),
        "system_prompt": u.get("system_prompt", ""),
        "auth_provider": u.get("auth_provider", "email")
    }

@app.put("/api/me/name")
def update_name(request: UpdateNameRequest, user=Depends(get_current_user)):
    if len(request.name.strip()) < 2:
        raise HTTPException(status_code=400, detail="Name too short")
    update_user_name(user["id"], request.name.strip())
    return {"message": "Name updated"}

@app.put("/api/me/password")
def update_password(request: UpdatePasswordRequest, user=Depends(get_current_user)):
    u = get_user_by_id(user["id"])
    if not u.get("password"):
        raise HTTPException(status_code=400, detail="This account signed up with Google and has no password set. Use 'Continue with Google' to sign in.")
    if not bcrypt.checkpw(request.current_password.encode(), u["password"].encode()):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(request.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    hashed = bcrypt.hashpw(request.new_password.encode(), bcrypt.gensalt()).decode()
    update_user_password(user["id"], hashed)
    return {"message": "Password updated"}

@app.put("/api/me/model")
def update_model(request: UpdateModelRequest, user=Depends(get_current_user)):
    if request.model not in AVAILABLE_MODELS:
        raise HTTPException(status_code=400, detail="Invalid model")
    update_default_model(user["id"], request.model)
    return {"message": "Model updated"}

@app.put("/api/me/system-prompt")
def update_prompt(request: UpdateSystemPromptRequest, user=Depends(get_current_user)):
    update_system_prompt(user["id"], request.system_prompt)
    return {"message": "System prompt updated"}

@app.delete("/api/me/history")
def clear_all(user=Depends(get_current_user)):
    delete_all_history(user["id"])
    return {"message": "All history cleared"}

@app.get("/api/models")
def get_models():
    return {"models": AVAILABLE_MODELS}

@app.post("/chat")
def chat(request: ChatRequest, user=Depends(get_current_user)):
    u = get_user_by_id(user["id"])
    if not u:
        raise HTTPException(status_code=401, detail="User not found. Please log out and log in again.")
    model = request.model if request.model in AVAILABLE_MODELS else u.get("default_model", "llama-3.3-70b-versatile")
    system_prompt = u.get("system_prompt", "")
    save_message(request.session_id, user["id"], "user", request.message)
    history = get_history(request.session_id)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    # history rows now carry created_at (for timestamps in the UI) - the Groq API
    # only accepts role/content, so strip the extra field before sending it up.
    messages.extend({"role": h["role"], "content": h["content"]} for h in history)

    def generate():
        full_reply = ""
        try:
            stream = client.chat.completions.create(model=model, messages=messages, stream=True)
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    full_reply += delta
                    yield delta
        finally:
            # Save whatever was generated even if the client disconnected/aborted mid-stream,
            # so a "stopped" reply isn't silently lost from history.
            if full_reply:
                save_message(request.session_id, user["id"], "assistant", full_reply)

    return StreamingResponse(generate(), media_type="text/plain")

@app.post("/retry")
def retry(request: ChatRequest, user=Depends(get_current_user)):
    u = get_user_by_id(user["id"])
    if not u:
        raise HTTPException(status_code=401, detail="User not found. Please log out and log in again.")
    model = request.model if request.model in AVAILABLE_MODELS else u.get("default_model", "llama-3.3-70b-versatile")
    history = get_history(request.session_id)
    if history and history[-1]["role"] == "assistant":
        history = history[:-1]
    messages = [{"role": h["role"], "content": h["content"]} for h in history]
    response = client.chat.completions.create(model=model, messages=messages)
    reply = response.choices[0].message.content
    save_message(request.session_id, user["id"], "assistant", reply)
    return {"reply": reply}

@app.post("/edit-message")
def edit_message(request: ChatRequest, user=Depends(get_current_user)):
    delete_messages_after(request.session_id, request.message)
    return {"status": "deleted"}

@app.post("/generate-topic")
def generate_topic(request: TopicRequest, user=Depends(get_current_user)):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": f"Generate a very short 2-3 word title for a chat starting with: '{request.message}'. Reply with ONLY the title."}]
    )
    return {"topic": response.choices[0].message.content.strip()}

@app.post("/save-topic")
def save_topic_endpoint(request: SaveTopicRequest, user=Depends(get_current_user)):
    save_topic(request.session_id, user["id"], request.topic)
    return {"status": "saved"}

@app.get("/topics")
def topics(user=Depends(get_current_user)):
    return {"topics": get_all_topics(user["id"]), "pinned": get_pinned_sessions(user["id"])}

@app.post("/toggle-pin")
def toggle_pin_endpoint(request: PinRequest, user=Depends(get_current_user)):
    is_pinned = toggle_pin(request.session_id, user["id"])
    return {"pinned": is_pinned}

@app.post("/upload-image")
async def upload_image(session_id: str = Form(...), file: UploadFile = File(...), user=Depends(get_current_user)):
    contents = await file.read()
    content_type = file.content_type or "image/jpeg"

    # The #1 cause of slow image analysis is sending a full-resolution phone photo
    # (often 3000px+, several MB) straight to the vision model - more pixels means
    # more image tokens means much longer inference. Downscaling to a max of 1024px
    # keeps plenty of detail for "describe this image" while cutting analysis time
    # dramatically. Falls back to the original bytes if Pillow isn't installed.
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(contents))
        img = img.convert("RGB")
        img.thumbnail((1024, 1024))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        contents = buf.getvalue()
        content_type = "image/jpeg"
    except Exception as e:
        print("Image resize skipped:", e)

    b64 = base64.b64encode(contents).decode("utf-8")
    data_url = f"data:{content_type};base64,{b64}"
    # Persist the user side immediately so the thumbnail survives a reload even if
    # the model call below is slow or fails.
    save_message(session_id, user["id"], "user", f"[[image]]{data_url}")

    def generate():
        full_reply = ""
        try:
            stream = client.chat.completions.create(
                model="meta-llama/llama-4-maverick-17b-128e-instruct",
                messages=[{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": "Describe this image in detail."}
                ]}],
                stream=True
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    full_reply += delta
                    yield delta
        finally:
            if full_reply:
                save_message(session_id, user["id"], "assistant", full_reply)

    return StreamingResponse(generate(), media_type="text/plain")

@app.post("/upload-file")
async def upload_file(session_id: str = Form(...), file: UploadFile = File(...), user=Depends(get_current_user)):
    contents = await file.read()
    text = ""

    if file.filename.lower().endswith(".pdf"):
        try:
            import pypdf
        except ImportError:
            save_message(session_id, user["id"], "user", f"📄 {file.filename}")
            reply = "I can't read PDFs right now because the `pypdf` library isn't installed on the server. Run `pip install pypdf` and try again."
            save_message(session_id, user["id"], "assistant", reply)
            return {"reply": reply}
        try:
            import io
            reader = pypdf.PdfReader(io.BytesIO(contents))
            pages_text = [(page.extract_text() or "") for page in reader.pages]
            text = " ".join(t for t in pages_text if t.strip())
        except Exception as e:
            print("PDF extraction error:", e)
            text = ""  # don't fall back to decoding raw PDF bytes as text - that's garbage input
    else:
        try:
            text = contents.decode("utf-8")
        except UnicodeDecodeError:
            text = ""

    save_message(session_id, user["id"], "user", f"📄 {file.filename}")

    if not text.strip():
        reply = (
            "I couldn't extract any readable text from this file. If it's a scanned/image-based PDF "
            "(no selectable text), text extraction won't work on it - try a text-based PDF, DOCX exported as PDF, "
            "or a .txt file instead."
        )
        save_message(session_id, user["id"], "assistant", reply)
        return {"reply": reply}

    text = text[:6000]
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": f"Summarize this document clearly:\n\n{text}"}]
    )
    reply = response.choices[0].message.content
    save_message(session_id, user["id"], "assistant", reply)
    return {"reply": reply}

@app.post("/share-chat")
def share_chat(request: ShareChatRequest, user=Depends(get_current_user)):
    share_id = str(uuid.uuid4())[:8]
    save_shared_chat(share_id, request.session_id, user["id"])
    return {"share_url": f"{APP_BASE_URL}/share/{share_id}"}

@app.get("/api/share/{share_id}")
def get_share(share_id: str):
    shared = get_shared_chat(share_id)
    if not shared:
        raise HTTPException(status_code=404, detail="Shared chat not found")
    history = get_history(shared["session_id"])
    return {"history": history}

@app.get("/history")
def history(session_id: str, user=Depends(get_current_user)):
    return {"history": get_history(session_id)}

@app.get("/sessions")
def sessions(user=Depends(get_current_user)):
    return {"sessions": get_all_sessions(user["id"])}

@app.delete("/history")
def clear(session_id: str, user=Depends(get_current_user)):
    delete_history(session_id)
    return {"message": "Chat cleared"}