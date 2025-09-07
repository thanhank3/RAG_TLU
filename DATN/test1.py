import chromadb
import pandas as pd

# Kết nối lại với ChromaDB
client = chromadb.PersistentClient(path=r"D:\DATN\Output\chroma_db")

# Lấy Collection
collection = client.get_collection(name="rag_collection")

# Lấy toàn bộ dữ liệu
results = collection.get()  # Trả về: {'ids': [...], 'documents': [...], 'embeddings': [...]}

# Tạo DataFrame
df = pd.DataFrame({
    'id': results['ids'],
    'document': results['documents']
    # Nếu muốn lưu cả embeddings thì thêm dòng dưới:
    # 'embedding': results['embeddings']
})

# Xuất ra file CSV
output_path = r"D:\DATN\Output\chroma_data.csv"
df.to_csv(output_path, index=False, encoding='utf-8-sig')

print(f"✅ Đã xuất {len(df)} dòng dữ liệu ra file: {output_path}")
