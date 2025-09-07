import pandas as pd
from langchain_chroma import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
import re

# Khởi tạo BGE-M3 embedding
embedding_model = HuggingFaceEmbeddings(model_name="BAAI/bge-m3")

# Kết nối với ChromaDB hiện tại
vectorstore = Chroma(
    collection_name="rag_collection",
    embedding_function=embedding_model,
    persist_directory="D:/DATN/Output/chroma_db"
)

# Đọc dữ liệu mới từ file CSV
df = pd.read_csv("D:/DATN/Output/chroma_data.csv")  # Điều chỉnh đường dẫn

# Chuẩn bị dữ liệu mới từ file CSV
new_documents = []
new_metadatas = []
new_ids = []

for idx, row in df.iterrows():
    doc = row['document']
    doc_id = row['id']

    # Trích xuất metadata từ nội dung tài liệu
    student_id = re.search(r"Mã sinh viên: (\d+)", doc)
    student_id = student_id.group(1) if student_id else "unknown"
    semester = re.search(r"Học kỳ: ([\w_]+)", doc)
    semester = semester.group(1) if semester else ""

    new_documents.append(doc)
    new_metadatas.append({"student_id": student_id, "semester": semester})
    new_ids.append(doc_id)

# Thêm dữ liệu mới mà không xóa dữ liệu cũ
vectorstore.add_texts(
    texts=new_documents,
    metadatas=new_metadatas,
    ids=new_ids
)

print(f"Added {len(new_documents)} new documents to ChromaDB")