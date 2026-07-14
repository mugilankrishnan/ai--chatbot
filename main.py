from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import Groq
import os, base64, bcrypt, jwt, uuid, httpx
from db import (init_db, save_message, get_history, delete_history,
    get_all_sessions, delete_messages_after, save_topic, get_all_topics,
    create_user, get_user_by_email, get_user_by_id, get_user_by_google_id,
    create_google_user, link_google_id_to_user, update_user_name,
    update_user_password, update_default_model, update_system_prompt,
    delete_all_history, save_shared_chat, get_shared_chat)

load_dotenv()
app = FastAPI()
init_db()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "nova_ai_secret_key_2026")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")
security = HTTPBearer()

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
def signup(request: SignupRequest):
    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    hashed = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt()).decode()
    user_id = create_user(request.name, request.email, hashed)
    if not user_id:
        raise HTTPException(status_code=400, detail="Email already exists")
    token = jwt.encode({"id": user_id, "name": request.name, "email": request.email}, SECRET_KEY, algorithm="HS256")
    return {"token": token, "name": request.name}

@app.post("/login")
def login(request: LoginRequest):
    user = get_user_by_email(request.email)
    if not user or not bcrypt.checkpw(request.password.encode(), user["password"].encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")
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
    model = request.model if request.model in AVAILABLE_MODELS else u.get("default_model", "llama-3.3-70b-versatile")
    system_prompt = u.get("system_prompt", "")
    save_message(request.session_id, user["id"], "user", request.message)
    history = get_history(request.session_id)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history)
    response = client.chat.completions.create(model=model, messages=messages)
    reply = response.choices[0].message.content
    save_message(request.session_id, user["id"], "assistant", reply)
    return {"reply": reply}

@app.post("/retry")
def retry(request: ChatRequest, user=Depends(get_current_user)):
    u = get_user_by_id(user["id"])
    model = request.model if request.model in AVAILABLE_MODELS else u.get("default_model", "llama-3.3-70b-versatile")
    history = get_history(request.session_id)
    if history and history[-1]["role"] == "assistant":
        history = history[:-1]
    response = client.chat.completions.create(model=model, messages=history)
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
    return {"topics": get_all_topics(user["id"])}

@app.post("/upload-image")
async def upload_image(file: UploadFile = File(...), user=Depends(get_current_user)):
    contents = await file.read()
    b64 = base64.b64encode(contents).decode("utf-8")
    response = client.chat.completions.create(
        model="meta-llama/llama-4-maverick-17b-128e-instruct",
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:{file.content_type};base64,{b64}"}},
            {"type": "text", "text": "Describe this image in detail."}
        ]}]
    )
    return {"reply": response.choices[0].message.content}

@app.post("/upload-file")
async def upload_file(file: UploadFile = File(...), user=Depends(get_current_user)):
    contents = await file.read()
    if file.filename.endswith(".pdf"):
        try:
            import pypdf, io
            reader = pypdf.PdfReader(io.BytesIO(contents))
            text = " ".join([page.extract_text() for page in reader.pages if page.extract_text()])
        except:
            text = contents.decode("utf-8", errors="ignore")
    else:
        text = contents.decode("utf-8", errors="ignore")
    text = text[:3000]
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": f"Summarize this document clearly:\n\n{text}"}]
    )
    return {"reply": response.choices[0].message.content}

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