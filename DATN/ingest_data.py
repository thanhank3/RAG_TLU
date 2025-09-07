import os
import pandas as pd
from collections import defaultdict
from sentence_transformers import SentenceTransformer
import chromadb
from unstructured.partition.auto import partition
from unstructured.chunking.basic import chunk_elements
from langchain.text_splitter import RecursiveCharacterTextSplitter
import re

# ==== Cấu hình ====
input_dir = r"D:\DATN\input_files"
output_dir = r"D:\DATN\Output3"
os.makedirs(output_dir, exist_ok=True)

# ==== Khởi tạo ChromaDB ====
client = chromadb.PersistentClient(path=os.path.join(output_dir, "chroma_db"))
collection = client.get_or_create_collection(name="rag_collection")


# ==== Nếu đã có dữ liệu → không làm lại ====
if collection.count() > 0:
    print(f"Chroma đã có {collection.count()} đoạn. Không cần xử lý lại.")
    exit()

# ==== Tải model SentenceTransformer ====
model = SentenceTransformer("BAAI/bge-m3")

# ==== Ingest dữ liệu ====
file_count = 0
for filename in os.listdir(input_dir):
    file_path = os.path.join(input_dir, filename)
    if not os.path.isfile(file_path):
        continue

    print(f" Đang xử lý file: {filename}")
    try:
        chunk_texts = []
        metadatas = []

        if filename.lower().endswith((".xlsx", ".xls")):
            xlsx = pd.read_excel(file_path, sheet_name=None)
            for sheet_name, df in xlsx.items():
                df = df.fillna("").astype(str)
                df.columns = df.columns.str.strip().str.lower()

                # === File điểm sinh viên ===
                if "mã sinh viên" in df.columns and "tên học phần" in df.columns:
                    grouped_by_msv = defaultdict(list)

                    for _, row in df.iterrows():
                        msv = row.get("mã sinh viên", "")
                        grouped_by_msv[msv].append(row)

                    for msv, rows in grouped_by_msv.items():
                        # Lọc môn trùng → giữ điểm cao hơn
                        unique_courses = {}
                        for row in rows:
                            ma_hp = row.get("mã học phần", "").strip()
                            diem_chu = row.get("điểm chữ", "").strip().upper()
                            diem_thang4 = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}.get(diem_chu, 0)
                            if ma_hp not in unique_courses or diem_thang4 > unique_courses[ma_hp]['diem']:
                                unique_courses[ma_hp] = {
                                    'row': row,
                                    'diem': diem_thang4
                                }

                        # Tính tổng TC và tổng TC × điểm
                        tong_tc = 0
                        tong_tc_diem = 0
                        mon_list = []
                        for info in unique_courses.values():
                            row = info['row']
                            diem_chu = row.get("điểm chữ", "").strip().upper()
                            if diem_chu == "F":
                                continue
                            ma_hp = row.get("mã học phần", "").upper()
                            ten = row.get("tên học phần", "").lower()
                            try:
                                tc = float(row.get("số tc", "0"))
                            except:
                                continue
                            # Loại Tiếng Anh tăng cường, Thể chất 1 TC
                            if "tăng cường" in ten or ma_hp.startswith("TATC"):
                                continue
                            if tc == 1 and any(kw in ten for kw in ["bóng chuyền", "cầu lông", "cờ vua", "quần vợt"]):
                                continue
                            diem_thang4 = {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0}.get(diem_chu, 0)
                            tong_tc += tc
                            tong_tc_diem += tc * diem_thang4
                            mon_list.append(row)

                        gpa = round(tong_tc_diem / tong_tc, 2) if tong_tc > 0 else 0

                        joined = f"[Dữ liệu điểm toàn khóa]\nMã sinh viên: {msv}\nTổng số tín chỉ tích lũy: {tong_tc}\nTổng điểm x tín chỉ: {tong_tc_diem:.2f}\nGPA toàn khóa: {gpa}\n\nDanh sách môn học:\n"
                        for row in mon_list:
                            joined += f"- {row.get('tên học phần', '')} ({row.get('mã học phần', '')}), TC: {row.get('số tc', '')}, TKHP: {row.get('tkhp', '')}, Điểm chữ: {row.get('điểm chữ', '')}\n"

                        chunk_texts.append(joined.strip())
                        metadatas.append({
                            "loai": "tong_ket",
                            "msv": msv,
                            "tong_tin_chi": tong_tc,
                            "tong_tc_x_diem": round(tong_tc_diem, 2),
                            "gpa_toankhoa": gpa
                        })

                        # Tính GPA từng học kỳ
                        grouped_by_sem = defaultdict(list)
                        for row in rows:
                            hoc_ky = row.get("học kỳ", "Không rõ học kỳ")
                            grouped_by_sem[hoc_ky].append(row)

                        for hoc_ky, sem_rows in grouped_by_sem.items():
                            tong_tc_hk = 0
                            tong_tc_diem_hk = 0
                            mon_list_hk = []

                            for row in sem_rows:
                                diem_chu = row.get("điểm chữ", "").strip().upper()
                                if diem_chu == "F":
                                    continue
                                ma_hp = row.get("mã học phần", "").upper()
                                ten = row.get("tên học phần", "").lower()
                                try:
                                    tc = float(row.get("số tc", "0"))
                                except:
                                    continue
                                if "tăng cường" in ten or ma_hp.startswith("TATC"):
                                    continue
                                if tc == 1 and any(kw in ten for kw in ["bóng chuyền", "cầu lông", "cờ vua", "quần vợt"]):
                                    continue
                                diem_thang4 = {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0}.get(diem_chu, 0)
                                tong_tc_hk += tc
                                tong_tc_diem_hk += tc * diem_thang4
                                mon_list_hk.append(row)

                            gpa_hk = round(tong_tc_diem_hk / tong_tc_hk, 2) if tong_tc_hk > 0 else 0

                            joined_sem = f"[Dữ liệu điểm sinh viên]\nMã sinh viên: {msv}\nHọc kỳ: {hoc_ky}\nGPA học kỳ: {gpa_hk}\n\nDanh sách môn học:\n"
                            for row in sem_rows:
                                joined_sem += f"- {row.get('tên học phần', '')} ({row.get('mã học phần', '')}), TC: {row.get('số tc', '')}, Điểm quá trình: {row.get('quá trình', '')}, Điểm thi: {row.get('thi', '/')}, TKHP: {row.get('tkhp', '')}, Điểm chữ: {row.get('điểm chữ', '')}\n"

                            chunk_texts.append(joined_sem.strip())
                            metadatas.append({
                                "loai": "diem",
                                "msv": msv,
                                "học_kỳ": hoc_ky,
                                "gpa_hocky": gpa_hk,
                                "tong_tc_hk": tong_tc_hk,
                                "tong_tc_diem_hk": round(tong_tc_diem_hk, 2)
                            })

                elif "mã học phần" in df.columns and "tên học phần" in df.columns:
                    for _, row in df.iterrows():
                        text_content = f"""[Dữ liệu môn học]
                        Mã học phần: {row.get('mã học phần', '')}
                        Tên học phần: {row.get('tên học phần', '')}
                        Số tín chỉ: {row.get('số tín chỉ', row.get('số tc', ''))}
                        Học kỳ: {row.get('học kỳ', '')}
                        Khối kiến thức: {row.get('khối kiến thức', '')}
                        """
                        chunk_texts.append(text_content.strip())
                        metadatas.append({
                            "loai": "mon_hoc",
                            "mã_môn": row.get("mã học phần", ""),
                            "tên_môn": row.get("tên học phần", ""),
                            "số_tín_chỉ": row.get("số tín chỉ", row.get("số tc", "")),
                            "học_kỳ": row.get("học kỳ", ""),
                            "nhom": row.get("khối kiến thức", "").strip().lower()
                        })
                else:
                    print(f" File {filename} không đúng định dạng dự kiến.")


        elif filename.lower().endswith((".docx", ".pdf", ".txt")):
            elements = partition(filename=file_path)
            raw_text = "\n".join(el.text for el in elements)


            # 2. Làm sạch (giữ xuống dòng để split chính xác)
            def clean_text(text):
                import unicodedata
                text = unicodedata.normalize("NFC", text)
                text = text.replace("\u200b", "").replace("\x0c", "")
                text = text.replace("\t", " ").replace("\xa0", " ")
                text = re.sub(r"[ ]{2,}", " ", text)
                text = "\n".join(line.strip() for line in text.splitlines())
                return re.sub(r"\n{3,}", "\n\n", text).strip()


            cleaned_text = clean_text(raw_text)

            # 3. Tạo chunker có overlap
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=512,
                chunk_overlap=50,
                separators=["\n\n", "\n", ". ", " "]
            )

            chunks = splitter.split_text(cleaned_text)

            # 4. Lưu từng chunk
            for i, chunk in enumerate(chunks):
                chunk_texts.append(chunk.strip())
                metadatas.append({
                    "loai": "quy_che",
                    "file": filename,
                    "chunk_index": i
                })

        else:
            print(f" Không hỗ trợ định dạng {filename}. Bỏ qua.")
            continue

        if chunk_texts:
            embeddings = model.encode(chunk_texts, batch_size=32, show_progress_bar=True, normalize_embeddings=True)
            collection.add(
                embeddings=embeddings.tolist(),
                documents=chunk_texts,
                metadatas=metadatas,
                ids=[f"{file_count}_{i}" for i in range(len(chunk_texts))]
            )
            print(f" Đã xử lý {len(chunk_texts)} đoạn từ {filename}")
            file_count += 1
        else:
            print(f" Không tìm thấy nội dung hợp lệ trong {filename}")

    except Exception as e:
        print(f" Lỗi khi xử lý {filename}: {e}")

# ==== Tổng kết ====
print(f"Tổng số đoạn đã lưu vào Chroma: {collection.count()}")