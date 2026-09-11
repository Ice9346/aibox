import json
import os
import shutil
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import fitz  # PyMuPDF
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

app = FastAPI()

# เปิด CORS เพื่อให้หน้าเว็บจาก Vercel ส่งข้อมูลเข้ามาได้
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

KNOWLEDGE_FILE = "latest_lesson.json"
LOGS_FILE = "question_logs.json"

# โหลดโมเดล Embedding มารอไว้บน RAM ของ Server
print("⏳ โหลดโมเดล Embedding...")
embedder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")


class LogEntry(BaseModel):
  question: str
  answer: str


# --- API สำหรับอาจารย์ (ผ่านเว็บ Vercel) ---


@app.post("/upload_pdf")
async def upload_pdf(file: UploadFile = File(...)):
  temp_path = f"temp_{file.filename}"
  with open(temp_path, "wb") as buffer:
    shutil.copyfileobj(file.file, buffer)

  # 1. สกัดข้อความจาก PDF
  doc = fitz.open(temp_path)
  full_text = "".join([page.get_text() for page in doc])
  doc.close()
  os.remove(temp_path)

  # 2. หั่นข้อความเป็นท่อนๆ
  chunk_size = 350
  overlap = 50
  chunks = []
  for i in range(0, len(full_text), chunk_size - overlap):
    c = full_text[i : i + chunk_size].strip()
    if len(c) > 30:
      chunks.append(c)

  # 3. แปลงเป็น Vector
  embeddings = embedder.encode(chunks, show_progress_bar=False).tolist()

  # 4. อัปเดตเวอร์ชันและเซฟลงไฟล์ JSON
  current_version = 1
  if os.path.exists(KNOWLEDGE_FILE):
    try:
      with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
        old_data = json.load(f)
        current_version = old_data.get("version", 0) + 1
    except:
      pass

  payload = {
      "version": current_version,
      "total_chunks": len(chunks),
      "data": [
          {"text": c, "embedding": e} for c, e in zip(chunks, embeddings)
      ],
  }

  with open(KNOWLEDGE_FILE, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False)

  return {"status": "success", "version": current_version, "chunks": len(chunks)}


@app.get("/view_logs")
async def view_logs():
  """ให้อาจารย์เปิดดูประวัติคำถามที่เด็กถาม"""
  if os.path.exists(LOGS_FILE):
    with open(LOGS_FILE, "r", encoding="utf-8") as f:
      return json.load(f)
  return []


# --- API สำหรับกล่อง Jetson Orin Nano ---


@app.get("/check_version")
async def check_version():
  """กล่องจะยิงมาถามบ่อยๆ ว่ามีบทเรียนใหม่ไหม"""
  if os.path.exists(KNOWLEDGE_FILE):
    with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
      data = json.load(f)
      return {"version": data.get("version", 0)}
  return {"version": 0}


@app.get("/download_lesson")
async def download_lesson():
  """กล่องดาวน์โหลดข้อมูล Vector ทั้งก้อนไปเซฟลง SSD"""
  if os.path.exists(KNOWLEDGE_FILE):
    with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
      return json.load(f)
  return {"version": 0, "data": []}


@app.post("/log_question")
async def log_question(entry: LogEntry):
  """กล่องส่งประวัติคำถาม-คำตอบกลับมาบันทึกบน Server"""
  logs = []
  if os.path.exists(LOGS_FILE):
    try:
      with open(LOGS_FILE, "r", encoding="utf-8") as f:
        logs = json.load(f)
    except:
      logs = []

  logs.append({"question": entry.question, "answer": entry.answer})

  with open(LOGS_FILE, "w", encoding="utf-8") as f:
    json.dump(logs, f, ensure_ascii=False, indent=2)

  return {"status": "recorded"}