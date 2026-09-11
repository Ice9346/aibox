import json
import os
import numpy as np
import requests

SERVER_URL = "https://web-production-3eb56.up.railway.app"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_LESSON_FILE = os.path.join(BASE_DIR, "synced_lesson.json")

# 1. ฟังก์ชันดึงบทเรียนจาก Railway มาเก็บไว้ในเครื่อง
def sync_lesson():
    print("🔄 กำลังตรวจสอบบทเรียนใหม่จากเซิร์ฟเวอร์...")
    try:
        res = requests.get(f"{SERVER_URL}/check_version", timeout=10)
        server_ver = res.json().get("version", 0)
        
        local_ver = 0
        if os.path.exists(LOCAL_LESSON_FILE):
            with open(LOCAL_LESSON_FILE, "r", encoding="utf-8") as f:
                local_ver = json.load(f).get("version", 0)
                
        if server_ver > local_ver or not os.path.exists(LOCAL_LESSON_FILE):
            print(f"📥 พบเวอร์ชันใหม่ (v{server_ver}) กำลังดาวน์โหลดข้อมูล...")
            dl_res = requests.get(f"{SERVER_URL}/download_lesson", timeout=30)
            lesson_data = dl_res.json()
            
            with open(LOCAL_LESSON_FILE, "w", encoding="utf-8") as f:
                json.dump(lesson_data, f, ensure_ascii=False)
            print(f"✅ บันทึกบทเรียนใหม่ลงเครื่องเรียบร้อย! ({lesson_data.get('total_chunks', 0)} ท่อน)")
        else:
            print(f"👌 บทเรียนในเครื่องเป็นเวอร์ชันล่าสุดแล้ว (v{local_ver})")
    except Exception as e:
        print(f"⚠️ ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์ได้: {e} (ใช้บทเรียนออฟไลน์ที่มีอยู่)")

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def ask_ollama(question, context):
    prompt = f"""คุณคือผู้ช่วยครูอัจฉริยะ จงตอบคำถามต่อไปนี้โดยใช้เฉพาะข้อมูลใน [เนื้อหาอ้างอิง] เท่านั้น 
หากไม่มีข้อมูล ให้ตอบว่า "ในบทเรียนนี้ไม่ได้ระบุข้อมูลเรื่องดังกล่าวไว้ครับ"

[เนื้อหาอ้างอิง]:
{context}

[คำถาม]:
{question}

[คำตอบ]:"""

    payload = {
        "model": "qwen2.5:3b",
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2}
    }
    res = requests.post("http://localhost:11434/api/generate", json=payload)
    return res.json()["response"]

def send_log_to_server(question, answer):
    try:
        requests.post(
            f"{SERVER_URL}/log_question",
            json={"question": question, "answer": answer},
            timeout=5
        )
    except:
        pass

# --- เริ่มการทำงาน ---
if __name__ == "__main__":
    # ตรวจสอบและดึงบทเรียนล่าสุด
    sync_lesson()
    
    if not os.path.exists(LOCAL_LESSON_FILE):
        print("❌ ยังไม่มีไฟล์บทเรียนในเครื่อง กรุณาอัปโหลด PDF ผ่านเว็บก่อน")
        exit()
        
    with open(LOCAL_LESSON_FILE, "r", encoding="utf-8") as f:
        lesson_data = json.load(f)
        
    chunks = [item["text"] for item in lesson_data["data"]]
    embeddings = np.array([item["embedding"] for item in lesson_data["data"]])
    
    print("⏳ โหลดเอนจินประมวลผลคำถาม...")
    from fastembed import TextEmbedding
    embedder = TextEmbedding(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    
    print("\n" + "=" * 50)
    print("🤖 กล่องพร้อมตอบคำถามจากบทเรียนที่ซิงค์มาแล้ว!")
    print("=" * 50)
    
    while True:
        question = input("\n🗣️ เด็กถามว่า (หรือพิมพ์ 'exit'): ")
        if question.lower() == "exit":
            break
            
        # คำนวณเวกเตอร์คำถาม
        q_vec = list(embedder.embed([question]))[0]
        
        # ค้นหาข้อความที่ตรงกัน
        scores = [cosine_similarity(q_vec, c_vec) for c_vec in embeddings]
        top_indices = np.argsort(scores)[::-1][:2]
        relevant_context = "\n---\n".join([chunks[i] for i in top_indices])
        
        # ถาม AI
        print("🤔 กำลังคิดคำตอบ...")
        answer = ask_ollama(question, relevant_context)
        print(f"\n💡 คำตอบ:\n{answer}")
        
        # ส่ง Log กลับขึ้นเว็บ
        send_log_to_server(question, answer)
        print("📤 บันทึกคำถามขึ้นเว็บแล้ว")
