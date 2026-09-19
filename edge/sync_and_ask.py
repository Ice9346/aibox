import json
import os
import threading
import time
import tkinter as tk
from fastembed import TextEmbedding
from faster_whisper import WhisperModel
import numpy as np
import requests
import sounddevice as sd

# ================= Configuration =================
SAMPLE_RATE = 16000
SERVER_URL = "https://web-production-3eb56.up.railway.app"
LOCAL_LESSON_FILE = "synced_lesson.json"
OLLAMA_MODEL = "qwen2.5:3b" # ถ้าเครื่องไม่รองรับให้ใช้ qwen2.5:0.5b

# Global Variables & Locks
stt_model = None
embedder = None
chunks = []
embeddings = None

is_recording = False
is_processing = False
audio_chunks = []
state_lock = threading.Lock()


# ================= 1. Auto-Sync Lesson Module =================
def sync_lesson():
  """ตรวจสอบเวอร์ชันและดาวน์โหลดบทเรียนจาก Railway"""
  print("🔄 กำลังตรวจสอบบทเรียนใหม่จากเซิร์ฟเวอร์...")
  try:
    res = requests.get(f"{SERVER_URL}/check_version", timeout=6)
    server_ver = res.json().get("version", 0)

    local_ver = 0
    if os.path.exists(LOCAL_LESSON_FILE):
      with open(LOCAL_LESSON_FILE, "r", encoding="utf-8") as f:
        local_ver = json.load(f).get("version", 0)

    if server_ver > local_ver or not os.path.exists(LOCAL_LESSON_FILE):
      print(f"📥 พบเวอร์ชันใหม่ (v{server_ver}) กำลังดาวน์โหลด...")
      dl_res = requests.get(f"{SERVER_URL}/download_lesson", timeout=30)
      lesson_data = dl_res.json()

      with open(LOCAL_LESSON_FILE, "w", encoding="utf-8") as f:
        json.dump(lesson_data, f, ensure_ascii=False)
      msg = f"อัปเดตบทเรียนใหม่ v{server_ver} แล้ว ({lesson_data.get('total_chunks', 0)} ท่อน)"
      print(f"✅ {msg}")
      return True, msg
    else:
      msg = f"บทเรียนเป็นเวอร์ชันล่าสุดแล้ว (v{local_ver})"
      print(f"👌 {msg}")
      return True, msg
  except Exception as e:
    msg = "โหมดออฟไลน์ (เชื่อมต่อเซิร์ฟเวอร์ไม่ได้)"
    print(f"⚠️ {msg}: {e}")
    return False, msg


def load_cached_lesson():
  """โหลดเวกเตอร์และเนื้อหาบทเรียนเข้าสู่ RAM"""
  global chunks, embeddings
  if os.path.exists(LOCAL_LESSON_FILE):
    try:
      with open(LOCAL_LESSON_FILE, "r", encoding="utf-8") as f:
        lesson_data = json.load(f)
      data = lesson_data.get("data", [])
      chunks = [item["text"] for item in data]
      embeddings = np.array([item["embedding"] for item in data])
      print(f"📚 โหลดบทเรียนเข้าหน่วยความจำสำเร็จ ({len(chunks)} ท่อน)")
    except Exception as e:
      print(f"❌ โหลดไฟล์แคชล้มเหลว: {e}")


# ================= 2. Offline RAG & LLM Module =================
def cosine_similarity(a, b):
  denom = np.linalg.norm(a) * np.linalg.norm(b)
  if denom == 0:
    return 0.0
  return np.dot(a, b) / denom


def send_log_async(question, answer):
  """ส่ง Log กลับไปที่เว็บเบื้องหลังโดยไม่ให้กระทบ GUI"""

  def log_worker():
    try:
      requests.post(
          f"{SERVER_URL}/log_question",
          json={"question": question, "answer": answer},
          timeout=5,
      )
      print("📤 บันทึกประวัติคำถามขึ้นเว็บสำเร็จ")
    except Exception:
      pass

  threading.Thread(target=log_worker, daemon=True).start()


def get_ai_answer(question):
  global embedder, chunks, embeddings
  relevant_context = ""

  # RAG Search ด้วย FastEmbed
  if embedder is not None and embeddings is not None and len(chunks) > 0:
    try:
      q_vec = list(embedder.embed([question]))[0]
      scores = [cosine_similarity(q_vec, c_vec) for c_vec in embeddings]
      top_indices = np.argsort(scores)[::-1][:2]
      relevant_context = "\n---\n".join([chunks[i] for i in top_indices])
    except Exception as e:
      print(f"RAG Error: {e}")

  # Prompt สไตล์ sync_and_ask เดิม
  prompt = f"""คุณคือผู้ช่วยครูอัจฉริยะ จงตอบคำถามต่อไปนี้โดยใช้เฉพาะข้อมูลใน [เนื้อหาอ้างอิง] เท่านั้น 
หากไม่มีข้อมูล ให้ตอบว่า "ในบทเรียนนี้ไม่ได้ระบุข้อมูลเรื่องดังกล่าวไว้ครับ"

[เนื้อหาอ้างอิง]:
{relevant_context}

[คำถาม]:
{question}

[คำตอบ]:"""

  payload = {
      "model": OLLAMA_MODEL,
      "prompt": prompt,
      "stream": False,
      "options": {"temperature": 0.2},
  }

  try:
    res = requests.post(
        "http://localhost:11434/api/generate", json=payload, timeout=30
    )
    answer = res.json().get("response", "").strip()
  except Exception as e:
    answer = f"ไม่สามารถประมวลผลคำตอบได้ ({e})"

  send_log_async(question, answer)
  return answer


# ================= 3. Audio & STT Module =================
def toggle_recording():
  global is_recording, is_processing

  with state_lock:
    if is_processing or stt_model is None or embedder is None:
      return

    if not is_recording:
      is_recording = True
      btn_talk.config(text="⏹️ กดเพื่อส่งคำถาม", bg="#f38ba8")
      status_label.config(
          text="🎙️ กำลังฟังเสียง... พูดคำถามได้เลย", fg="#f38ba8"
      )
      transcript_label.config(text="")
      answer_box.delete("1.0", tk.END)

      def stream_worker():
        global audio_chunks
        audio_chunks = []
        try:
          with sd.InputStream(
              samplerate=SAMPLE_RATE, channels=1, dtype="float32"
          ) as stream:
            while is_recording:
              data, _ = stream.read(1024)
              audio_chunks.append(data.copy())
        except Exception as e:
          print(f"Audio InputStream Error: {e}")

      threading.Thread(target=stream_worker, daemon=True).start()

    else:
      is_recording = False
      is_processing = True

      status_label.config(text="⏳ กำลังถอดเสียงและคิดคำตอบ...", fg="#f9e2af")
      btn_talk.config(
          text="⏳ กำลังประมวลผล...",
          bg="#6c7086",
          fg="#ffffff",
          state=tk.DISABLED,
      )

      def worker():
        global is_processing
        time.sleep(0.3)

        if not audio_chunks:
          finish_with_ui("⚠️ ไม่พบสัญญาณเสียง ลองกดใหม่อีกครั้ง")
          return

        raw_audio = np.concatenate(audio_chunks, axis=0).flatten()

        if len(raw_audio) < (SAMPLE_RATE * 0.4):
          finish_with_ui("⚠️ เวลาพูดสั้นเกินไป ลองกดใหม่อีกครั้ง")
          return

        try:
          segments, _ = stt_model.transcribe(
              raw_audio,
              language="th",
              initial_prompt="บทเรียน การเรียน วิทยาศาสตร์ วงจรไฟฟ้า คำถาม",
              beam_size=3,
          )
          question = "".join([s.text for s in segments]).strip()

          if not question:
            finish_with_ui("⚠️ ฟังไม่ชัดเจน ลองกดพูดใหม่อีกครั้งครับ")
            return

          root.after(
              0,
              lambda: transcript_label.config(
                  text=f'คำถามของหนู: "{question}"'
              ),
          )
          root.after(
              0,
              lambda: status_label.config(
                  text="🧠 AI กำลังค้นหาคำตอบ...", fg="#89b4fa"
              ),
          )

          reply = get_ai_answer(question)

          def show_result():
            status_label.config(text="✨ คำตอบจากบทเรียน:", fg="#a6e3a1")
            answer_box.delete("1.0", tk.END)
            answer_box.insert(tk.END, reply)
            btn_talk.config(
                text="🎙️ กดเพื่อพูดถาม",
                bg="#89b4fa",
                fg="#1e1e2e",
                state=tk.NORMAL,
            )

          root.after(0, show_result)

        except Exception as e:
          print(f"Pipeline Error: {e}")
          finish_with_ui("❌ เกิดข้อผิดพลาดในการประมวลผล")
        finally:
          is_processing = False

      threading.Thread(target=worker, daemon=True).start()


def finish_with_ui(msg):
  global is_processing
  is_processing = False

  def update():
    status_label.config(text=msg, fg="#fab387")
    btn_talk.config(
        text="🎙️ กดเพื่อพูดถาม",
        bg="#89b4fa",
        fg="#1e1e2e",
        state=tk.NORMAL,
    )

  root.after(0, update)


# ================= 4. GUI Setup =================
root = tk.Tk()
root.title("AI Learning Box")
root.geometry("800x540")
root.configure(bg="#1e1e2e")

title_lbl = tk.Label(
    root,
    text="🤖 ห้องเรียนอัจฉริยะ (AI Learning Box)",
    font=("Ubuntu", 20, "bold"),
    fg="#cdd6f4",
    bg="#1e1e2e",
)
title_lbl.pack(pady=8)

sync_status_lbl = tk.Label(
    root,
    text="📡 กำลังตรวจสอบบทเรียนจากเซิร์ฟเวอร์...",
    font=("Ubuntu", 10),
    fg="#a6adc8",
    bg="#1e1e2e",
)
sync_status_lbl.pack(pady=2)

status_label = tk.Label(
    root,
    text="⏳ กำลังเตรียมความพร้อมระบบ...",
    font=("Ubuntu", 14, "bold"),
    fg="#f9e2af",
    bg="#1e1e2e",
)
status_label.pack(pady=4)

btn_talk = tk.Button(
    root,
    text="⏳ กำลังโหลดโมเดล...",
    font=("Ubuntu", 15, "bold"),
    bg="#6c7086",
    fg="#ffffff",
    padx=25,
    pady=8,
    relief="flat",
    state=tk.DISABLED,
    command=toggle_recording,
)
btn_talk.pack(pady=6)

transcript_label = tk.Label(
    root,
    text="",
    font=("Ubuntu", 13, "italic"),
    fg="#bac2de",
    bg="#1e1e2e",
    wraplength=720,
)
transcript_label.pack(pady=4)

answer_box = tk.Text(
    root,
    font=("Ubuntu", 14),
    fg="#ffffff",
    bg="#313244",
    wrap="word",
    relief="flat",
    padx=20,
    pady=12,
)
answer_box.pack(expand=True, fill="both", padx=30, pady=8)


# ================= 5. Background Initialization =================
def init_system():
  global stt_model, embedder

  # 1. เช็กซิงค์บทเรียน และโหลดข้อมูลแคช
  _, sync_msg = sync_lesson()
  load_cached_lesson()
  root.after(0, lambda: sync_status_lbl.config(text=f"📚 {sync_msg}"))

  # 2. โหลด FastEmbed สำหรับ Vector Search
  print("⏳ กำลังโหลด FastEmbed...")
  cache_path = os.path.expanduser("~/.cache/fastembed")
  embedder = TextEmbedding(
      model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
      cache_dir=cache_path,
  )

  # 3. โหลด Faster-Whisper STT
  print("⏳ กำลังโหลด Whisper STT...")
  stt_model = WhisperModel("large", device="cpu", compute_type="int8") #ถ้าเครื่องไม่รองรับให้ใช้ tiny

  def ready_ui():
    status_label.config(text="👉 คลิกที่ปุ่มด้านล่างเพื่อเริ่มพูด", fg="#89b4fa")
    btn_talk.config(
        text="🎙️ กดเพื่อพูดถาม",
        bg="#89b4fa",
        fg="#1e1e2e",
        state=tk.NORMAL,
        cursor="hand2",
    )

  root.after(0, ready_ui)
  print("🚀 ระบบ AI Learning Box พร้อมใช้งานสมบูรณ์!")


threading.Thread(target=init_system, daemon=True).start()

root.mainloop()