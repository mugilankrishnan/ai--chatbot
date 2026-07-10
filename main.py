from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import Groq
import os, base64, bcrypt, jwt
from db import (
    init_db, save_message, get_history, delete_history, get_all_sessions,
    delete_messages_after, save_topic, get_all_topics, create_user,
    get_user_by_email, get_user_by_google_id, create_google_user,
    link_google_id_to_user,
)

load_dotenv()
app = FastAPI()
init_db()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
SESSION_SECRET = os.getenv("SESSION_SECRET_KEY")

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
security = HTTPBearer()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")

oauth = OAuth()
oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


class ChatRequest(BaseModel):
    session_id: str
    message: str

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


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=["HS256"])
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


def make_token(user_id, name, email):
    return jwt.encode({"id": user_id, "name": name, "email": email}, SECRET_KEY, algorithm="HS256")


@app.get("/", response_class=HTMLResponse)
def home():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/login", response_class=HTMLResponse)
def login_page():
    with open("login.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/auth-success", response_class=HTMLResponse)
def auth_success_page():
    with open("auth-success.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/style.css")
def style():
    return FileResponse("style.css", media_type="text/css")

@app.get("/script.js")
def script():
    return FileResponse("script.js", media_type="application/javascript")


@app.post("/signup")
def signup(request: SignupRequest):
    hashed = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt()).decode()
    user_id = create_user(request.name, request.email, hashed)
    if not user_id:
        raise HTTPException(status_code=400, detail="Email already exists")
    token = make_token(user_id, request.name, request.email)
    return {"token": token, "name": request.name}

@app.post("/login")
def login(request: LoginRequest):
    user = get_user_by_email(request.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email")
    if user.get("auth_provider") == "google":
        raise HTTPException(status_code=400, detail="This email uses Google sign-in. Please continue with Google.")
    if not bcrypt.checkpw(request.password.encode(), user["password"].encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = make_token(user["id"], user["name"], user["email"])
    return {"token": token, "name": user["name"]}


@app.get("/auth/google/login")
async def google_login(request: Request):
    redirect_uri = f"{APP_BASE_URL}/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/google/callback")
async def google_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo")
    if not userinfo:
        raise HTTPException(status_code=400, detail="Could not fetch Google profile")

    google_id = userinfo["sub"]
    email = userinfo["email"]
    name = userinfo.get("name", email.split("@")[0])

    user = get_user_by_google_id(google_id)

    if not user:
        existing = get_user_by_email(email)
        if existing:
            link_google_id_to_user(existing["id"], google_id)
            user_id, user_name = existing["id"], existing["name"]
        else:
            user_id = create_google_user(name, email, google_id)
            user_name = name
    else:
        user_id, user_name = user["id"], user["name"]

    jwt_token = make_token(user_id, user_name, email)
    return RedirectResponse(url=f"/auth-success?token={jwt_token}&name={user_name}")


@app.post("/chat")
def chat(request: ChatRequest, user=Depends(get_current_user)):
    save_message(request.session_id, user["id"], "user", request.message)
    history = get_history(request.session_id)
    response = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=history)
    reply = response.choices[0].message.content
    save_message(request.session_id, user["id"], "assistant", reply)
    return {"reply": reply}

@app.post("/retry")
def retry(request: ChatRequest, user=Depends(get_current_user)):
    history = get_history(request.session_id)
    if history and history[-1]["role"] == "assistant":
        history = history[:-1]
    response = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=history)
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
        model="meta-llama/llama-4-scout-17b-16e-instruct",
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
        except Exception:
            text = contents.decode("utf-8", errors="ignore")
    else:
        text = contents.decode("utf-8", errors="ignore")
    text = text[:3000]
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": f"Summarize this document clearly:\n\n{text}"}]
    )
    return {"reply": response.choices[0].message.content, "filename": file.filename}

@app.get("/history")
def history(session_id: str, user=Depends(get_current_user)):
    return {"history": get_history(session_id)}

@app.get("/sessions")
def sessions(user=Depends(get_current_user)):
    return {"sessions": get_all_sessions(user["id"])}

@app.delete("/history")
def clear(session_id: str, user=Depends(get_current_user)):
    delete_history(session_id)
    return {"message": "Chat cleared successfully"}