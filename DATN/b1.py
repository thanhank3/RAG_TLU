from chromadb import PersistentClient

# === Cấu hình ===
chroma_path = r"D:\DATN\Output3\chroma_db"   # Thay đường dẫn nếu cần
collection_name = "rag_collection"

# === Kết nối ChromaDB ===
client = PersistentClient(path=chroma_path)

# Với Chroma >= 0.6.0: list_collections trả về list tên
collections = client.list_collections()
print("📂 Các collection hiện có:", collections)

if collection_name not in collections:
    raise ValueError(f"❌ Collection '{collection_name}' không tồn tại. Hãy kiểm tra lại tên.")

collection = client.get_collection(name=collection_name)

# === In toàn bộ nội dung đã ingest ===
total = collection.count()
print(f"\n Tổng số đoạn đã ingest: {total}\n")

# === Lấy và in từng đoạn
results = collection.get(include=["documents", "metadatas", "embeddings"])
docs = results["documents"]
metas = results["metadatas"]
embeds = results["embeddings"]

for i, (doc, meta, emb) in enumerate(zip(docs, metas, embeds)):
    print(f"\nChunk {i}:")
    print(doc.strip())
    print("Metadata:", meta)
    print("Vector embedding (rút gọn):", emb[:5], "...")
    print("-" * 50)
