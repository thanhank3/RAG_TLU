from sentence_transformers import SentenceTransformer, util
from rouge_scorer import rouge_scorer
import pandas as pd

# Load mô hình nhúng
model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

def evaluate_pair(reference, prediction):
    # Semantic similarity (cosine similarity)
    emb1 = model.encode(reference, convert_to_tensor=True)
    emb2 = model.encode(prediction, convert_to_tensor=True)
    semantic_sim = float(util.cos_sim(emb1, emb2)[0][0])

    # ROUGE-L
    scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
    rouge_scores = scorer.score(reference, prediction)
    rouge_l_f1 = rouge_scores["rougeL"].fmeasure

    return semantic_sim, rouge_l_f1

# Ví dụ dữ liệu đánh giá
examples = [
    {
        "student_id": "123456",
        "reference": "Môn Hệ thống thông tin địa lý có 3 tín chỉ, thuộc nhóm chuyên ngành.",
        "predicted": "Môn Hệ thống thông tin địa lý thuộc nhóm chuyên ngành và có 3 tín chỉ.",
    },
    {
        "student_id": "123457",
        "reference": "GPA toàn khóa của bạn là 3.2, xếp loại Giỏi theo quy chế.",
        "predicted": "Theo quy chế, GPA 3.2 được xếp loại Giỏi.",
    },
    # Thêm ví dụ khác nếu cần
]

# Đánh giá
results = []
for ex in examples:
    semantic, rouge_l = evaluate_pair(ex["reference"], ex["predicted"])
    results.append({
        "Student ID": ex.get("student_id", ""),
        "Reference": ex["reference"],
        "Prediction": ex["predicted"],
        "Semantic": round(semantic, 4),
        "ROUGE-L": round(rouge_l, 4)
    })

# Xuất kết quả thành bảng
df = pd.DataFrame(results)
print(df)
