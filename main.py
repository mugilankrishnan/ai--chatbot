from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import Groq
import os
from db import init_db, save_message, get_history, delete_history

load_dotenv()
app = FastAPI()
init_db()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

class ChatRequest(BaseModel):
    session_id: str
    message: str

@app.get("/", response_class=HTMLResponse)
def home():
    with open("index.html", "r") as f:
        return f.read()

@app.post("/chat")
def chat(request: ChatRequest):
    save_message(request.session_id, "user", request.message)
    history = get_history(request.session_id)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=history
    )
    reply = response.choices[0].message.content
    save_message(request.session_id, "assistant", reply)
    return {"reply": reply}

@app.get("/history")
def history(session_id: str):
    return {"history": get_history(session_id)}

@app.delete("/history")
def clear(session_id: str):
    delete_history(session_id)
    return {"message": "Chat cleared successfully"}