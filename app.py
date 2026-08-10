import streamlit as st
import faiss
import numpy as np
import os
import json
import uuid
from datetime import datetime
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
import google.generativeai as genai

load_dotenv()

# ตั้งค่า Gemini API
api_key = os.getenv("GOOGLE_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

# 1. โหลดโมเดล Sentence Transformer สำหรับแปลงข้อความเป็น Vector


@st.cache_resource
def load_embedder():
    return SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

# 2. โหลด menu_kb.md และตัดเป็น Chunks


@st.cache_resource
def load_kb_chunks():
    kb_path = "menu_kb.md"
    if not os.path.exists(kb_path):
        return ["MilkLab° ร้านเครื่องดื่มนมสด ชา กาแฟ เปิด 08:00 - 18:00 น."]
    with open(kb_path, "r", encoding="utf-8") as f:
        text = f.read()
    chunks = [c.strip() for c in text.split("\n\n") if c.strip()]
    return chunks

# 3. สร้าง FAISS Index จาก Chunks


@st.cache_resource
def build_faiss_index(_embedder, chunks):
    embeddings = _embedder.encode(chunks)
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(np.array(embeddings, dtype=np.float32))
    return index

# ฟังก์ชันบันทึก Observability Trace ลง traces.jsonl


def log_trace(trace_data):
    with open("traces.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(trace_data, ensure_ascii=False) + "\n")

# 4. ฟังก์ชันค้นหา Top-K Chunks


def retrieve_top_k(query, embedder, index, chunks, k=3):
    query_vector = embedder.encode([query])
    distances, indices = index.search(
        np.array(query_vector, dtype=np.float32), k)
    retrieved = [chunks[i] for i in indices[0] if i < len(chunks)]
    return retrieved, distances[0].tolist()

# 5. ฟังก์ชันสร้างคำตอบด้วย Gemini


# 5. ฟังก์ชันสร้างคำตอบด้วย Gemini
# 5. ฟังก์ชันสร้างคำตอบด้วย Gemini
def generate_answer(query, context_chunks):
    context = "\n---\n".join(context_chunks)
    prompt = f"""คุณคือผู้ช่วยตอบคำถามประจำร้าน MilkLab° จงตอบคำถามลูกค้าโดยอ้างอิงจากข้อมูลบริบทต่อไปนี้อย่างถูกต้องและเป็นมิตร:

[บริบทข้อมูล]:
{context}

[คำถาม]: {query}
[คำตอบ]:"""

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "⚠️ กรุณาตรวจสอบว่าได้ตั้งค่า GOOGLE_API_KEY ในไฟล์ .env เรียบร้อยแล้ว"

    genai.configure(api_key=api_key)

    # รายชื่อโมเดลรุ่นใหม่ที่เปิดใช้งานจริง
    candidate_models = [
        "gemini-flash-latest",
        "gemini-1.5-flash-latest",
        "gemini-1.5-flash",
        "gemini-1.5-pro-latest"
    ]

    last_err = ""
    for model_name in candidate_models:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            if response.text:
                return response.text
        except Exception as e:
            last_err = str(e)
            continue

    return f"เกิดข้อผิดพลาดในการเชื่อมต่อ Gemini: {last_err}"


def main():
    st.set_page_config(page_title="MilkLab° RAG", page_icon="🥛")
    st.title("MilkLab° RAG Chatbot")
    st.caption("ถามอะไรเกี่ยวกับ MilkLab ได้ ตอบจาก menu_kb.md")

    embedder = load_embedder()
    chunks = load_kb_chunks()
    index = build_faiss_index(embedder, chunks)

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("ถามคำถามเกี่ยวกับร้าน MilkLab° เช่น เมนูแนะนำ, เวลาเปิดปิด..."):
        trace_id = str(uuid.uuid4())
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            top_chunks, distances = retrieve_top_k(
                prompt, embedder, index, chunks, k=3)
            answer = generate_answer(prompt, top_chunks)
            st.markdown(answer)

            # แสดง Trace Observability ใน expander ใต้คำตอบ
            with st.expander("🔍 Trace (Retrieved Contexts)"):
                for i, (c, d) in enumerate(zip(top_chunks, distances), 1):
                    st.markdown(f"**Chunk {i} (Distance: {d:.4f}):**\n{c}")

            # บันทึกลง traces.jsonl
            log_trace({
                "trace_id": trace_id,
                "timestamp": datetime.utcnow().isoformat(),
                "query": prompt,
                "retrieved_chunks": top_chunks,
                "distances": distances,
                "answer": answer
            })

        st.session_state.messages.append(
            {"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
