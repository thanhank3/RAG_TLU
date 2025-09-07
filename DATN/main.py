import os
import re
import json
import time
from dotenv import load_dotenv
import gradio as gr
import openai
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_core.output_parsers import StrOutputParser

#  ENV , MODELS
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError(" Không tìm thấy OPENAI_API_KEY trong file .env")

# Embedding model
embedding_model = HuggingFaceEmbeddings(model_name="BAAI/bge-m3")

# Vector DB
vectorstore = Chroma(
    collection_name="rag_collection",
    embedding_function=embedding_model,
    persist_directory="D:/DATN/Output3/chroma_db",
)

#  PROMPT

prompt_unified = PromptTemplate.from_template(
    """
    Bạn là trợ lý ảo hỗ trợ tra cứu kết quả học tập. 
    Chỉ sử dụng thông tin bên dưới khi câu hỏi thực sự liên quan đến truy vấn kết quả học tập, môn học hoặc quy chế đào tạo.
    {context}
    Câu hỏi trước: {prev_question}
    Trả lời trước: {prev_answer}

    Câu hỏi hiện tại: {question}
    Mã sinh viên (nếu có): {student_id}

    Thông tin dưới đây chỉ sử dụng nếu câu hỏi có liên quan:
    - Tổng tín chỉ tích lũy: {tong_tin_chi}
    - Tổng điểm x tín chỉ: {tong_tc_x_diem}
    - GPA toàn khóa: {gpa_toankhoa}
    - Danh sách môn học thêm: {danh_sach_mon_them}
    - Danh sách môn học lại: {danh_sach_mon_hoc_lai}
    - Điểm cũ của môn học lại: {diem_cu_mon_hoc_lai}

    Hướng dẫn:
    - Nếu câu hỏi liên quan đến điểm số hoặc GPA (chứa 'điểm', 'gpa', 'học thêm', 'học lại', 'tín chỉ tích lũy', 'tkhp'):
      1. Bỏ qua các môn có điểm F, môn GDTC 1 tín chỉ.
      2. Với môn học lại, nếu điểm mới thấp hơn điểm cũ, giữ điểm cũ.
      3. Tính GPA mới sau khi xử lý các bước trên.
      4. Quy đổi điểm chữ: A=4, B=3, C=2, D=1, F=0.
      5. So sánh GPA mới và GPA cũ, giải thích sự thay đổi nếu có.
      6. Nếu không đủ dữ liệu, trả lời: "Không tìm thấy thông tin điểm số hoặc GPA."

    - Nếu câu hỏi là thống kê điểm chữ (chứa "tỉ lệ điểm chữ", "bao nhiêu điểm A", "phổ điểm", "thống kê điểm A B C D F"):
      1. Tính tổng số môn theo từng điểm chữ (A, B, C, D, F).
      2. Tính tỉ lệ phần trăm theo công thức: số môn loại đó / tổng số môn * 100%.
      3. Không loại trừ điểm F.

    - Nếu câu hỏi liên quan đến thông tin môn học (chứa 'môn', 'môn học', 'thông tin môn', 'tkhp'):
      1. Trích xuất thông tin môn học (mã, tên, tín chỉ, nhóm) từ context.
      2. Nếu không có thông tin, trả lời: "Không tìm thấy thông tin về môn học."

    - Nếu câu hỏi liên quan đến quy chế (chứa 'quy chế', 'điều kiện', 'tốt nghiệp', 'xếp loại'):
      1. So sánh GPA với quy chế tốt nghiệp (So sánh GPA với quy chế tốt nghiệp:
           - 3.60 – 4.00: Xuất sắc
           - 3.20 – 3.59: Giỏi
           - 2.50 – 3.19: Khá
           - 2.00 – 2.49: Trung bình Khá
           - 1.00 – 1.99: Trung bình
           - Dưới 1.00: Kém).
      2. Trích xuất và trả lời đúng nội dung quy chế nếu có.
      3. Với môn GDTC, cần trên 5.0 mới tính là qua.
      - Nếu câu hỏi liên quan đến cảnh báo học tập (chứa "cảnh báo học tập", "bị cảnh báo", "học lực yếu"):
          1. Dựa vào GPA các học kỳ và số tín chỉ điểm F còn tồn (loại trừ GDTC, QPAN).
          2. Áp dụng quy chế sau:
             - Học kỳ đầu tiên: nếu GPA < 0.80 → cảnh báo.
             - Các học kỳ khác: nếu GPA < 1.00 → cảnh báo.
             - Nếu tổng tín chỉ điểm F > 24 → cảnh báo.
          3. Trả lời rõ sinh viên có bị cảnh báo không và lý do.

        - Nếu câu hỏi liên quan đến hạ bậc xếp loại tốt nghiệp (chứa "hạ bằng", "giảm xếp loại", "có bị trừ loại tốt nghiệp"):
          1. Chỉ áp dụng xếp loại tốt nghiệp ban đầu là Giỏi hoặc Xuất sắc (GPA ≥ 3.20), còn các xếp loại khác sẽ không bị hạ, thì:
             - Nếu tổng số tín chỉ từng bị điểm F > 5% tổng tín chỉ toàn khóa(140) → hạ bậc xếp loại.
             - Hoặc nếu sinh viên từng bị kỷ luật từ mức cảnh cáo trở lên → hạ bậc xếp loại.
          2. Nếu không đủ thông tin, ghi rõ chưa thể kết luận.

    - Nếu câu hỏi không liên quan đến học vụ, điểm số, GPA, môn học hoặc quy chế: chỉ trả lời một lời chào thân thiện.

   Trả lời bằng tiếng Việt một cách thân thiện, ngắn gọn, chính xác và dễ hiểu như 1 người trợ lý ảo thực thụ.
    """
)

#  RETRIEVER
Sc_KEYWORDS = [
    "điểm", "gpa",
    "học thêm", "học lại", "tkhp",
    "tín chỉ tích lũy", "qua môn", "đã qua", "tôi đã qua",
    "môn tôi đã qua", "tôi đã học xong", "tôi đã đậu môn", "tôi đậu môn", "đã đạt", "danh sách môn đã học",
    "tôi đã học", "tôi đã học môn", "tôi học môn", "môn thể chất", "tôi học những môn thể chất",
    "môn giáo dục thể chất", "môn tôi đã học", "tôi học những môn", "tôi học những môn thể chất nào",
    "tôi học thể chất nào",
]


def custom_retriever(query: str, student_id: str | None = None):
    """Truy xuất tài liệu phù hợp từ Chroma """
    q_lower = query.lower()

    # 1.  Truy vấn điểm 
    if student_id and any(k in q_lower for k in Sc_KEYWORDS):
        docs = vectorstore.similarity_search(
            query=query,
            k=30,
            filter={
                "$and": [
                    {"msv": {"$eq": student_id}},
                    {"loai": {"$in": ["diem", "tong_ket"]}}
                ]
            },
        )
        # Fallback: nếu rỗng → bỏ filter msv (đỡ “Không có thông tin”)
        if docs:
            return docs

    #  2.  Truy vấn thông tin môn học 
    code_match = re.search(r"\b[A-Z]{3}\d{3}\b", query)
    if code_match:
        code = code_match.group(0)
        return vectorstore.similarity_search(
            query=code,
            k=80,
            filter={
                "$and": [
                    {"mã_môn": {"$eq": code}},
                    {"loai": {"$eq": "mon_hoc"}}
                ]
            },
        )

    if any(k in q_lower for k in ["môn", "môn học", "thông tin môn"]):
        return vectorstore.similarity_search(
            query=query,
            k=150,
            filter={"loai": {"$eq": "mon_hoc"}},
        )

    # 3.  Quy chế / điều kiện
    if any(k in q_lower for k in
           ["quy chế", "điều kiện", "tốt nghiệp", "xếp loại",
            "điều khoản", "quy định", "loại", "gpa là gì", "thuộc loại"]):
        return vectorstore.similarity_search(
            query=query,
            k=60,
            filter={"loai": {"$eq": "quy_che"}},
        )

    #  4.  Mặc định
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
        temperature=0.2,
    )
except Exception as e:
    raise Exception(f"Lỗi khi khởi tạo LLM: {str(e)}")

rag_chain = (
        {
            "context": RunnableLambda(lambda x: format_docs(custom_retriever(x["question"], x.get("student_id")))),
            "question": RunnableLambda(lambda x: x.get("question", "")),
            "student_id": RunnableLambda(lambda x: x.get("student_id", "")),
            "prev_question": RunnableLambda(lambda x: x.get("prev_question", "")),
            "prev_answer": RunnableLambda(lambda x: x.get("prev_answer", "")),
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
                and meta.get("msv") == student_id
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
        if d.metadata.get("loai") == "tong_ket" and d.metadata.get("msv") == student_id:
            return (
                float(d.metadata.get("tong_tin_chi", 0)),
                float(d.metadata.get("tong_tc_x_diem", 0)),
                float(d.metadata.get("gpa_toankhoa", 0)),
            )
    return 0, 0, 0


# --- CHATBOT INTERFACE ---
prev_subject_state = gr.State("")  # lưu tên môn học trước đó


def chatbot_interface(query: str, student_id: str, prev_subject: str = "", prev_question: str = "",
                      prev_answer: str = ""):
    if not student_id or not re.fullmatch(r"\d{10}", student_id):
        return " Vui lòng nhập mã sinh viên.", prev_subject

    # Ngữ cảnh: nếu câu sau chứa "môn đó" → thay thế bằng prev_subject
    if "môn đó" in query.lower() or "môn này" in query.lower():
        if prev_subject:
            query = re.sub(r"môn đó", f"môn {prev_subject}", query, flags=re.IGNORECASE)
            query = query.lower().replace("môn này", f"môn {prev_subject}")
        else:
            return "Bạn cần hỏi rõ tên môn học trước.", prev_subject

    # Nếu câu hỏi chứa "môn ..." → cập nhật prev_subject
    match_mon = re.search(r"(?:môn(?: học)?\s+)([^\n\.,!?]+)", query.lower())
    current_subject = prev_subject
    if match_mon:
        raw = match_mon.group(1).strip(" .,:!?")
        if raw and len(raw) >= 3:
            current_subject = raw

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
        result = rag_chain.invoke({
            "question": query,
            "student_id": student_id,
            "prev_question": prev_question or "",
            "prev_answer": prev_answer or "",
            "tong_tin_chi": tong_tin_chi,
            "tong_tc_x_diem": tong_tc_x_diem,
            "gpa_toankhoa": gpa_toankhoa,
            "danh_sach_mon_them": danh_sach_mon_them,
            "danh_sach_mon_hoc_lai": danh_sach_mon_hoc_lai,
            "diem_cu_mon_hoc_lai": diem_cu_mon_hoc_lai,
        })
        return result.strip(), current_subject, query, result.strip()

    except openai.RateLimitError:
        time.sleep(7)  # Đợi 7 giây rồi thử lại một lần nữa
        try:
            result = rag_chain.invoke({
                "question": query,
                "student_id": student_id,
                "prev_question": prev_question or "",
                "prev_answer": prev_answer or "",
                "tong_tin_chi": tong_tin_chi,
                "tong_tc_x_diem": tong_tc_x_diem,
                "gpa_toankhoa": gpa_toankhoa,
                "danh_sach_mon_them": danh_sach_mon_them,
                "danh_sach_mon_hoc_lai": danh_sach_mon_hoc_lai,
                "diem_cu_mon_hoc_lai": diem_cu_mon_hoc_lai,
            })
            return result.strip(), current_subject, query, result.strip()
        except Exception as e:
            return f"Lỗi sau khi chờ do quá tải: {str(e)}", prev_subject, prev_question, prev_answer

    except Exception as e:
        return f"Lỗi: {str(e)}", prev_subject, prev_question, prev_answer


# ------------------- GRADIO UI -----------------------------

def set_student_id(student_id: str):
    if not re.fullmatch(r"\d{10}", student_id):
        return "MSV phải gồm đúng 10 chữ số.", ""
    return f" Đã lưu MSV: {student_id}", student_id


def build_ui():
    with gr.Blocks() as demo:
        gr.Markdown("## 🎓 Chatbot Học tập RAG – Tra cứu & GPA")
        sid_state = gr.State("")
        prev_subject_state = gr.State("")

        with gr.Row():
            sid_input = gr.Textbox(label=" MSV (10 chữ số)")
            save_btn = gr.Button(" Lưu MSV")
        sid_status = gr.Textbox(label="Trạng thái", interactive=False)
        save_btn.click(set_student_id, inputs=[sid_input], outputs=[sid_status, sid_state])

        gr.Markdown("###  Đặt câu hỏi")
        query_input = gr.Textbox(label="Câu hỏi", placeholder="Ví dụ: môn Hệ thống thông tin địa lý có mấy tín chỉ?")
        ask_btn = gr.Button("➡️ Gửi")
        answer_box = gr.Textbox(label="💬 Trả lời", lines=12)

        ask_btn.click(
            chatbot_interface,
            inputs=[query_input, sid_state, prev_subject_state],
            outputs=[answer_box, prev_subject_state],
        )

    return demo


if __name__ == "__main__":
    build_ui().launch()

