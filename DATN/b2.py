import os
import re
import json
import time
from dotenv import load_dotenv
import gradio as gr
import openai
from langchain_chroma import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_core.output_parsers import StrOutputParser

# ======================= ENV & MODELS =======================
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("❌ Không tìm thấy OPENAI_API_KEY trong file .env")

# Embedding model
embedding_model = HuggingFaceEmbeddings(model_name="BAAI/bge-m3")

# Vector DB (Chroma in persistent mode)
vectorstore = Chroma(
    collection_name="rag_collection",
    embedding_function=embedding_model,
    persist_directory="D:/DATN/Output/chroma_db",
)

# ----------------------- PROMPT -----------------------------
prompt_unified = PromptTemplate.from_template(
    """
Bạn là trợ lý ảo hỗ trợ tra cứu kết quả học tập.Dựa trên thông tin từ context:
{context}

Câu hỏi: {question}
Mã sinh viên (nếu có): {student_id}
Thông tin tổng kết (nếu có): - Tổng tín chỉ tích lũy: {tong_tin_chi}, - Tổng điểm x tín chỉ: {tong_tc_x_diem}, - GPA toàn khóa: {gpa_toankhoa}
Danh sách môn học thêm (nếu có): {danh_sach_mon_them}
Danh sách môn học lại (nếu có): {danh_sach_mon_hoc_lai}
Điểm cũ của môn học lại (nếu có): {diem_cu_mon_hoc_lai}

Hướng dẫn:
- Nếu câu hỏi liên quan đến điểm số hoặc GPA (chứa 'điểm', 'gpa', 'học thêm', 'học lại', 'tín chỉ tích lũy', 'tkhp'):
  1. Bỏ qua **mọi** môn học thêm/học lại có điểm **F** và bỏ qua những môn giáo dục thể chất(GDTC) 1 tín chỉ (không cộng vào GPA).
  2. Với môn học lại: nếu điểm mới thấp hơn điểm cũ, **giữ nguyên** điểm cũ.
  3. Sau khi xử lý hai quy tắc trên, tính GPA mới.
  4. Quy đổi điểm chữ: A=4, B=3, C=2, D=1, F=0.
  5. So sánh GPA mới với GPA cũ và giải thích sự thay đổi.
  6. Nếu không đủ dữ liệu, trả về: 'Không tìm thấy thông tin điểm số hoặc GPA.'
- Nếu câu hỏi liên quan đến thông tin môn học (chứa 'môn', 'môn học', 'thông tin môn', 'tkhp'):
  1. Trả về thông tin môn học (mã, tên, tín chỉ, nhóm) từ metadata hoặc nội dung context.
  2. Nếu không tìm thấy, trả về: 'Không tìm thấy thông tin về môn học.'
- Nếu câu hỏi liên quan đến quy chế (chứa 'quy chế', 'điều kiện', 'tốt nghiệp', 'xếp loại'):
  1. So sánh GPA với ngưỡng quy chế (3.20‑3.59 Giỏi, 2.50‑3.19 Khá, 2.30‑2.49 TB Khá, 2.00‑2.29 TB,Trung bình yếu từ 1,50 đến 1,99 Yếu từ 1,00 đến 1,49 Kém Dưới 1,00) và trả về xếp loại chính xác.
  2. Trả về thông tin quy chế phù hợp nếu có, hoặc 'Không tìm thấy thông tin quy chế.'
  3. Đối với các môn học giáo dục thể chất cần trên 5.0, nếu dưới 5.0 tuy hệ thống xét đạt nhưng vẫn chưa qua.
- Trả lời ngắn gọn, chính xác bằng tiếng Việt.
"""
)

# ------------------- RETRIEVER ------------------------------
GPA_KEYWORDS = [
    "điểm",
    "gpa",
    "học thêm",
    "học lại",
    "tkhp",
    "tín chỉ tích lũy",

]
def normalize_semester(query: str) -> str | None:
    # Ví dụ: học kỳ 1 năm 2021 → 1_2021_2022
    sem_match = re.search(r"(học[ ]?k[iì]|hk)[ ]?(\d)[ ]?(năm)?[ ]?(\d{4})", query, re.IGNORECASE)
    if sem_match:
        sem = sem_match.group(2)
        year = int(sem_match.group(4))
        next_year = year + 1
        return f"{sem}_{year}_{next_year}"

    # Ví dụ: học kỳ 2 2023-2024
    sem_match2 = re.search(r"(học[ ]?k[iì]|hk)[ ]?(\d)[ ]?(\d{4})[ -_](\d{4})", query, re.IGNORECASE)
    if sem_match2:
        sem = sem_match2.group(2)
        y1 = sem_match2.group(3)
        y2 = sem_match2.group(4)
        return f"{sem}_{y1}_{y2}"

    # Nếu người dùng đã nhập đúng định dạng
    sem_match3 = re.search(r"\d{1}_\d{4}_\d{4}", query)
    if sem_match3:
        return sem_match3.group(0)

    return None

def custom_retriever(query: str, student_id: str | None = None):
    """Lấy tài liệu phù hợp từ Chroma."""
    q_lower = query.lower()

    # --- Nếu hỏi điểm / GPA cá nhân -> cần filter theo mssv ---
    if student_id and student_id != "admin" and any(k in q_lower for k in GPA_KEYWORDS):
        return vectorstore.similarity_search(
            query=query,
            k=50,
            filter={
                "$and": [
                    {"mssv": {"$eq": student_id}},
                    {"$or": [{"loai": {"$eq": "diem"}}, {"loai": {"$eq": "tong_ket"}}]},
                ]
            },
        )
    if student_id:
        normalized_sem = normalize_semester(query)
        if normalized_sem:
            return vectorstore.similarity_search(
                query=normalized_sem,
                k=20,
                filter={
                    "$and": [
                        {"mssv": {"$eq": student_id}},
                        {"loai": {"$eq": "diem"}},
                        {"học_kỳ": {"$eq": normalized_sem}},
                    ]
                },
            )

    # --- Nếu hỏi thông tin môn học (theo mã hoặc tên) -> KHÔNG filter mssv ---
    code_match = re.search(r"\b[A-Z]{3}\d{3}\b", query)
    if code_match:
        code = code_match.group(0)
        return vectorstore.similarity_search(
            query=code,
            k=100,
            filter={"mã_môn": {"$eq": code}, "loai": {"$eq": "mon_hoc"}},
        )

    if any(k in q_lower for k in ["môn", "môn học", "thông tin môn"]):
        return vectorstore.similarity_search(
            query=query,
            k=200,
            filter={"loai": {"$eq": "mon_hoc"}},
        )

    # --- Quy chế ---
    if any(k in q_lower for k in ["quy chế", "điều kiện", "tốt nghiệp", "xếp loại"]):
        return vectorstore.similarity_search(
            query=query,
            k=100,
            filter={"loai": {"$eq": "quy_che"}},
        )

    # --- Mặc định ---
    return vectorstore.similarity_search(query=query, k=50)

# ------------------- ĐỊNH DẠNG TÀI LIỆU --------------------

def format_docs(docs):
    if isinstance(docs, list) and docs and isinstance(docs[0], str):
        return docs[0]
    out = []
    for doc in docs:
        meta = doc.metadata
        if meta.get("loai") == "mon_hoc":
            out.append(
                f"- {meta.get('tên_môn')} (mã: {meta.get('mã_môn')}, tín chỉ: {meta.get('số_tín_chỉ')}, nhóm: {meta.get('nhom')})"
            )
        else:
            out.append(f"- {doc.page_content}\nMetadata: {json.dumps(meta, ensure_ascii=False)}")
    return "\n".join(out)

# ------------------- LLM & RAG CHAIN -----------------------
try:
    llm = ChatOpenAI(
        api_key=api_key,
        model="gpt-4o",
        temperature=0.0,
    )
except Exception as e:
    raise Exception(f"❌ Lỗi khi khởi tạo LLM: {str(e)}")

rag_chain = (
    {
        "context": RunnableLambda(lambda x: format_docs(custom_retriever(x["question"], x.get("student_id")))),
        "question": RunnableLambda(lambda x: x.get("question", "")),
        "student_id": RunnableLambda(lambda x: x.get("student_id", "")),
        "danh_sach_mon_them": RunnableLambda(lambda x: x.get("danh_sach_mon_them", "")),
        "danh_sach_mon_hoc_lai": RunnableLambda(lambda x: x.get("danh_sach_mon_hoc_lai", "")),
        "diem_cu_mon_hoc_lai": RunnableLambda(lambda x: x.get("diem_cu_mon_hoc_lai", "")),
        "tong_tin_chi": RunnableLambda(lambda x: x.get("tong_tin_chi", 0)),
        "tong_tc_x_diem": RunnableLambda(lambda x: x.get("tong_tc_x_diem", 0)),
        "gpa_toankhoa": RunnableLambda(lambda x: x.get("gpa_toankhoa", 0)),
    }
    | prompt_unified
    | llm
    | StrOutputParser()
)

# ------------------- TIỆN ÍCH ------------------------------

def get_diem_cu_mon_hoc_lai(student_id: str, ten_mon: str, tin_chi: int):
    docs = custom_retriever(f"điểm môn {ten_mon}", student_id)
    diem_map = {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0}
    for d in docs:
        meta = d.metadata
        if (
            meta.get("loai") == "diem"
            and meta.get("mssv") == student_id
            and ten_mon.lower() in meta.get("ten_mon", "").lower()
            and int(meta.get("tin_chi", 0)) == tin_chi
        ):
            dc = meta.get("diem_chu")
            if dc not in diem_map:
                return f"- Điểm cũ của môn {ten_mon} không hợp lệ: {dc}."
            return f"- {ten_mon}, {tin_chi} tín chỉ, điểm cũ: {dc} ({diem_map[dc]} thang 4)"
    return f"- Không tìm thấy điểm cũ của môn {ten_mon}."


def get_tong_ket_info(student_id: str):
    docs = custom_retriever("thong tin tong ket", student_id)
    for d in docs:
        if d.metadata.get("loai") == "tong_ket" and d.metadata.get("mssv") == student_id:
            return (
                float(d.metadata.get("tong_tin_chi", 0)),
                float(d.metadata.get("tong_tc_x_diem", 0)),
                float(d.metadata.get("gpa_toankhoa", 0)),
            )
    return 0, 0, 0

# ----------- GỢI Ý MÔN CHƯA HỌC (NEXT COURSES) -------------

def suggest_next_courses(student_id: str) -> str:
    # 1. Truy xuất các môn sinh viên đã học (từ 'tong_ket' và 'diem')
    docs_done = vectorstore.similarity_search(
        query="tôi muốn xem điểm toàn khóa",
        k=100,
        filter={
            "$and": [
                {"mssv": {"$eq": student_id}},
                {"$or": [{"loai": {"$eq": "tong_ket"}}, {"loai": {"$eq": "diem"}}]}
            ]
        }
    )

    if not docs_done:
        return "❗ Không tìm thấy dữ liệu điểm cho sinh viên."

    # Lấy danh sách mã môn đã học
    mon_da_hoc = set()
    for doc in docs_done:
        for line in doc.page_content.split("\n"):
            if "(" in line and ")" in line:
                parts = line.split("(")
                if len(parts) >= 2:
                    ma_mon = parts[1].split(")")[0].strip()
                    if len(ma_mon) > 2:
                        mon_da_hoc.add(ma_mon.upper())

    # 2. Truy xuất toàn bộ môn học trong chương trình đào tạo
    all_subjects = vectorstore.similarity_search(
        query="danh sách chương trình đào tạo",
        k=200,
        filter={"loai": {"$eq": "mon_hoc"}}
    )

    # Lọc ra các môn chưa học (loại bỏ môn thể chất bằng điều kiện trong vòng for)
    remaining = []
    for doc in all_subjects:
        ma_mon = doc.metadata.get("mã_môn", "").upper()
        nhom = doc.metadata.get("nhom", "").lower()
        if ma_mon not in mon_da_hoc:
            # Bỏ qua môn thể chất
            if "thể chất" in nhom or ma_mon.startswith(("TH", "YG", "BC", "CL", "CV", "DK")):
                continue
            remaining.append(doc)

    # Sắp xếp theo học kỳ (nếu có)
    def sort_key(doc):
        try:
            return float(doc.metadata.get("học_kỳ", "99") or 99)
        except:
            return 99

    remaining.sort(key=sort_key)

    if not remaining:
        return "🎉 Bạn đã hoàn thành tất cả các môn trong chương trình đào tạo (ngoại trừ thể chất)."

    # Gợi ý 5-7 môn tiếp theo
    suggestions = remaining[:7]
    result = "📚 Gợi ý môn nên học tiếp:\n"
    for doc in suggestions:
        ma_mon = doc.metadata.get("mã_môn", "")
        ten_mon = doc.metadata.get("tên_môn", "")
        tc = doc.metadata.get("số_tín_chỉ", "")
        hk = doc.metadata.get("học_kỳ", "")
        result += f"- {ten_mon} (mã: {ma_mon}, {tc} TC, học kỳ {hk})\n"

    return result.strip()


# ------------------- CHATBOT INTERFACE ---------------------

def chatbot_interface(query: str, student_id: str):
    # 1. Yêu cầu MSSV trước
    if student_id != "admin" and any(found_id != student_id for found_id in re.findall(r"\b\d{10}\b", query)):
        return "❌ Bạn không được hỏi về thông tin của sinh viên khác."

    # 2. Không cho hỏi MSSV khác
    if any(found_id != student_id for found_id in re.findall(r"\b\d{10}\b", query)):
        return "❌ Bạn không được hỏi về thông tin của sinh viên khác."

    # 3. Nếu câu hỏi yêu cầu gợi ý môn nên học
    lower_q = query.lower()
    if any(k in lower_q for k in ["gợi ý", "nên học", "học tiếp", "môn nào nên học"]):
        return "📚 Gợi ý môn nên học tiếp:\n" + suggest_next_courses(student_id)

    # 4. Lấy thông tin tổng kết (nếu cần tính GPA)
    tong_tin_chi, tong_tc_x_diem, gpa_toankhoa = get_tong_ket_info(student_id)

    # 5. Trích xuất học thêm / học lại
    pattern_them = r"([\w\s]+),?\s*(\d+)\s*tín chỉ,?\s*điểm\s*([A-F])"
    pattern_hoclai = r"([\w\s]+),?\s*(\d+)\s*tín chỉ,?\s*(học lại|thi lại|làm lại)\s*được\s*([A-F])"

    mon_them = re.findall(pattern_them, query, re.IGNORECASE)
    mon_hoclai = re.findall(pattern_hoclai, query, re.IGNORECASE)

    danh_sach_mon_them = "\n".join(
        f"- {m[0].strip()}, {m[1]} tín chỉ, điểm {m[2].upper()}" for m in mon_them
    )
    danh_sach_mon_hoc_lai = "\n".join(
        f"- {m[0].strip()}, {m[1]} tín chỉ, điểm {m[3].upper()}" for m in mon_hoclai
    )
    diem_cu_mon_hoc_lai = "\n".join(
        get_diem_cu_mon_hoc_lai(student_id, m[0].strip(), int(m[1])) for m in mon_hoclai
    )

    # 6. Gọi RAG
    try:
        return rag_chain.invoke(
            {
                "question": query,
                "student_id": student_id,
                "tong_tin_chi": tong_tin_chi,
                "tong_tc_x_diem": tong_tc_x_diem,
                "gpa_toankhoa": gpa_toankhoa,
                "danh_sach_mon_them": danh_sach_mon_them,
                "danh_sach_mon_hoc_lai": danh_sach_mon_hoc_lai,
                "diem_cu_mon_hoc_lai": diem_cu_mon_hoc_lai,
            }
        ).strip()

    except openai.RateLimitError:
        time.sleep(7)
        return rag_chain.invoke(
            {
                "question": query,
                "student_id": student_id,
                "tong_tin_chi": tong_tin_chi,
                "tong_tc_x_diem": tong_tc_x_diem,
                "gpa_toankhoa": gpa_toankhoa,
                "danh_sach_mon_them": danh_sach_mon_them,
                "danh_sach_mon_hoc_lai": danh_sach_mon_hoc_lai,
                "diem_cu_mon_hoc_lai": diem_cu_mon_hoc_lai,
            }
        ).strip()

    except Exception as e:
        return f"❌ Lỗi khi xử lý câu hỏi: {str(e)}"

# ------------------- GRADIO UI -----------------------------

def set_student_id(student_id: str):
    if student_id != "admin" and not re.fullmatch(r"\d{10}", student_id):
        return "❌ MSSV phải gồm đúng 10 chữ số hoặc là 'admin'.", ""
    return f"✅ Đã lưu MSSV: {student_id}", student_id

def build_ui():
    with gr.Blocks() as demo:
        gr.Markdown("## 🎓 Chatbot Học tập RAG – Tra cứu & GPA")
        sid_state = gr.State("")

        with gr.Row():
            sid_input = gr.Textbox(label="🔑 MSSV (10 chữ số)")
            save_btn = gr.Button("💾 Lưu MSSV")
        sid_status = gr.Textbox(label="Trạng thái", interactive=False)
        save_btn.click(set_student_id, inputs=[sid_input], outputs=[sid_status, sid_state])

        gr.Markdown("### ❓ Đặt câu hỏi")
        query_input = gr.Textbox(label="Câu hỏi", placeholder="Ví dụ: môn Hệ thống thông tin địa lý có mấy tín chỉ? hoặc gợi ý môn nên học tiếp")
        ask_btn = gr.Button("➡️ Gửi")
        answer_box = gr.Textbox(label="💬 Trả lời", lines=12)

        ask_btn.click(chatbot_interface, inputs=[query_input, sid_state], outputs=answer_box)
    return demo


if __name__ == "__main__":
    build_ui().launch()
