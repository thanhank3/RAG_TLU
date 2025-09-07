# import os
# import json
# import chromadb
#
# output_dir = r"D:\DATN\Output"
#
# client = chromadb.PersistentClient(path=os.path.join(output_dir, "chroma_db"))
# collection = client.get_or_create_collection(name="rag_collection")
#
# # Lấy dữ liệu mà không request "ids"
# all_data = collection.get(include=["documents", "metadatas", "embeddings"])
#
# docs = []
# # Tạo id thủ công nếu cần vì "ids" không lấy được từ get
# for i in range(len(all_data["documents"])):
#     docs.append({
#         "id": str(i),  # Hoặc đặt id khác nếu bạn biết
#         "document": all_data["documents"][i],
#         "metadata": all_data["metadatas"][i],
#         # "embedding": all_data["embeddings"][i],  # Nếu cần thì thêm
#     })
#
# with open(os.path.join(output_dir, "chroma_export.json"), "w", encoding="utf-8") as f:
#     json.dump(docs, f, ensure_ascii=False, indent=4)
#
# print("✅ Đã xuất dữ liệu và metadata ra chroma_export.json")


import chromadb
import os
import json

# === Kết nối đến ChromaDB gốc ===
db_path = r"D:\DATN\Output3\chroma_db"
client = chromadb.PersistentClient(path=db_path)
collection = client.get_or_create_collection(name="rag_collection")

# === Lấy toàn bộ dữ liệu (document + metadata) ===
results = collection.get(include=["documents", "metadatas"])

# === Tạo danh sách dữ liệu cần lưu ===
data_list = []
for i in range(len(results["documents"])):
    item = {
        "document": results["documents"][i],
        "metadata": results["metadatas"][i]
    }
    data_list.append(item)

# === Ghi ra file JSON ===
output_file = r"D:\DATN\Output3\chroma_all_data.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(data_list, f, ensure_ascii=False, indent=4)

print(f"✅ Đã xuất {len(data_list)} đoạn dữ liệu ra file: {output_file}")
