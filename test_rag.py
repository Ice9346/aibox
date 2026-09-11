import os
import fitz  # PyMuPDF
import numpy as np
import requests
from sentence_transformers import SentenceTransformer

# 1. โหลดโมเดลแปลงประโยคเป็น Vector (รองรับภาษาไทย)
print("⏳ กำลังโหลดโมเดล Embedding...")
embedder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")


def extract_and_chunk(pdf_path, chunk_size=350, overlap=50):
  """อ่าน PDF และตัดเป็นท่อนๆ ขนาดพอดีคำ"""
  doc = fitz.open(pdf_path)
  full_text = ""
  for page in doc:
    full_text += page.get_text()
  doc.close()

  # ตัดท่อนข้อความแบบ overlap เพื่อไม่ให้บริบทขาด
  chunks = []
  for i in range(0, len(full_text), chunk_size - overlap):
    chunk = full_text[i : i + chunk_size].strip()
    if len(chunk) > 30:  # ข้ามท่อนที่สั้นเกินไป
      chunks.append(chunk)
  return chunks


def cosine_similarity(a, b):
  """คำนวณความคล้ายคลึงของ Vector ด้วย NumPy"""
  return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def ask_ollama(question, context):
  """ส่งข้อความเข้า Qwen 2.5 บังคับตอบตามเอกสารเท่านั้น (Strict RAG)"""
  prompt = f"""คุณคือผู้ช่วยครูอัจฉริยะ จงตอบคำถามต่อไปนี้โดยใช้เฉพาะข้อมูลที่ระบุใน [เนื้อหาอ้างอิง] เท่านั้น 
ห้ามแต่งเรื่องเพิ่ม หากไม่มีข้อมูลในเนื้อหา ให้ตอบสุภาพว่า "ในบทเรียนนี้ไม่ได้ระบุข้อมูลเรื่องดังกล่าวไว้ครับ"

[เนื้อหาอ้างอิง]:
{context}

[คำถาม]:
{question}

[คำตอบ]:"""

  payload = {
      "model": "qwen2.5:3b",
      "prompt": prompt,
      "stream": False,
      "options": {"temperature": 0.2},  # ตั้งค่าน้อยเพื่อลดการเพ้อเจ้อ
  }

  res = requests.post("http://localhost:11434/api/generate", json=payload)
  return res.json()["response"]


# --- เริ่มการทำงาน ---
if __name__ == "__main__":
  pdf_file = "sample.pdf"

  # ตรวจสอบว่ามีไฟล์ PDF ตัวอย่างหรือไม่
  if not os.path.exists(pdf_file):
    print(
        f"❌ ไม่พบไฟล์ '{pdf_file}' กรุณานำไฟล์ PDF วิชาการสั้นๆ มาวางในโฟลเดอร์นี้แล้วตั้งชื่อว่า {pdf_file}"
    )
    exit()

  print("📖 กำลังอ่านและตัดแบ่งเนื้อหาจาก PDF...")
  chunks = extract_and_chunk(pdf_file)
  print(f"✅ สกัดได้ทั้งหมด {len(chunks)} ท่อน")

  print("🧠 กำลังคำนวณ Vector สำหรับเนื้อหาทั้งหมด...")
  chunk_embeddings = embedder.encode(chunks, show_progress_bar=True)

  print("\n" + "=" * 50)
  print(" ระบบ RAG พร้อมแล้ว! ลองพิมพ์คำถามเกี่ยวกับเนื้อหาใน PDF ")
  print("=" * 50)

  while True:
    question = input("\n🗣️ ถามคำถาม (หรือพิมพ์ 'exit' เพื่อออก): ")
    if question.lower() == "exit":
      break

    # 1. แปลงคำถามเป็น Vector
    q_vec = embedder.encode(question)

    # 2. คำนวณหาท่อนที่ตรงกับคำถามที่สุด Top-2
    scores = [cosine_similarity(q_vec, c_vec) for c_vec in chunk_embeddings]
    top_indices = np.argsort(scores)[::-1][:2]

    relevant_context = "\n---\n".join([chunks[i] for i in top_indices])

    # 3. ให้ LLM สรุปคำตอบ
    print("🤖 AI กำลังคิดคำตอบ...")
    answer = ask_ollama(question, relevant_context)

    print(f"\n💡 คำตอบ:\n{answer}")