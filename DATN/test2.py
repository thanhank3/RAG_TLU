from transformers import AutoTokenizer, AutoModel
import torch
from rouge_score import rouge_scorer
import pandas as pd
import torch.nn.functional as F

# Load mô hình BGE-M3
model_name = "BAAI/bge-m3"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModel.from_pretrained(model_name)

# Hàm tính embedding
def get_bge_embedding(text):
    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
    with torch.no_grad():
        outputs = model(**inputs)
        embeddings = outputs.last_hidden_state[:, 0]  # Lấy CLS token
        embeddings = F.normalize(embeddings, p=2, dim=1)  # Chuẩn hóa
    return embeddings[0]

# Hàm tính điểm semantic và ROUGE-L
def evaluate_pair(reference, prediction):
    emb1 = get_bge_embedding(reference)
    emb2 = get_bge_embedding(prediction)
    semantic_sim = torch.cosine_similarity(emb1, emb2, dim=0).item()

    scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
    rouge_scores = scorer.score(reference, prediction)
    rouge_l_f1 = rouge_scores["rougeL"].fmeasure

    return semantic_sim, rouge_l_f1

# Giả lập hàm chatbot trả lời
def generate_answer(question):
    # TODO: thay bằng call API chatbot thật của bạn
    # Ở đây demo trả lời đơn giản (placeholder)
    return "Câu trả lời giả lập cho: " + question

# ==== Ví dụ đánh giá ====
examples = [
    {
        "student_id": "2151062697",
        "question": "GPA toàn khóa của tôi là bao nhiêu?",
        "reference": "GPA toàn khóa: 2.45."
    },
    {
        "student_id": "2151062697",
        "question": "Điểm môn Tiếng Anh 1 của tôi mấy điểm",
        "reference": "Điểm môn Tiếng Anh 1: 8.4, điểm chữ B."
    },
    {
        "student_id": "2151062697",
        "question": "Tôi được xếp loại gì?",
        "reference": "Xếp loại: Trung bình khá"
    },
    # Thêm các câu hỏi khác ở đây...
]

# ==== Đánh giá ====
results = []
for ex in examples:
    predicted = generate_answer(ex["question"])  # Sinh câu trả lời tự động
    semantic, rouge_l = evaluate_pair(ex["reference"], predicted)
    results.append({
        "Student ID": ex.get("student_id", ""),
        "Question": ex["question"],
        "Reference": ex["reference"],
        "Predicted": predicted,
        "Semantic": round(semantic, 4),
        "ROUGE-L": round(rouge_l, 4)
    })

# Xuất kết quả
df = pd.DataFrame(results)
df.to_excel("evaluation_results.xlsx", index=False)
print("✅ Đã lưu kết quả vào file evaluation_results.xlsx")
