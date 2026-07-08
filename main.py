from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import Groq
import os, base64
from db import init_db, save_message, get_history, delete_history, get_all_sessions, delete_messages_after, save_topic, get_all_topics

load_dotenv()
app = FastAPI()
init_db()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

class ChatRequest(BaseModel):
    session_id: str
    message: str

class TopicRequest(BaseModel):
    message: str

class SaveTopicRequest(BaseModel):
    session_id: str
    topic: str

@app.get("/", response_class=HTMLResponse)
def home():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/style.css")
def style():
    return FileResponse("style.css", media_type="text/css")

@app.get("/script.js")
def script():
    return FileResponse("script.js", media_type="application/javascript")

@app.post("/chat")
def chat(request: ChatRequest):
    save_message(request.session_id, "user", request.message)
    history = get_history(request.session_id)
    response = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=history)
    reply = response.choices[0].message.content
    save_message(request.session_id, "assistant", reply)
    return {"reply": reply}

@app.post("/retry")
def retry(request: ChatRequest):
    history = get_history(request.session_id)
    if history and history[-1]["role"] == "assistant":
        history = history[:-1]
    response = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=history)
    reply = response.choices[0].message.content
    save_message(request.session_id, "assistant", reply)
    return {"reply": reply}

@app.post("/edit-message")
def edit_message(request: ChatRequest):
    delete_messages_after(request.session_id, request.message)
    return {"status": "deleted"}

@app.post("/generate-topic")
def generate_topic(request: TopicRequest):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": f"Generate a very short 2-3 word title for a chat starting with: '{request.message}'. Reply with ONLY the title."}]
    )
    return {"topic": response.choices[0].message.content.strip()}

@app.post("/save-topic")
def save_topic_endpoint(request: SaveTopicRequest):
    save_topic(request.session_id, request.topic)
    return {"status": "saved"}

@app.get("/topics")
def topics():
    return {"topics": get_all_topics()}

@app.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
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
async def upload_file(file: UploadFile = File(...)):
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
    return {"reply": response.choices[0].message.content, "filename": file.filename}

@app.get("/history")
def history(session_id: str):
    return {"history": get_history(session_id)}

@app.get("/sessions")
def sessions():
    return {"sessions": get_all_sessions()}

@app.delete("/history")
def clear(session_id: str):
    delete_history(session_id)
    return {"message": "Chat cleared successfully"}