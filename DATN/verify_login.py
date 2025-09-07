import sqlite3, hashlib, os, re, smtplib, random, time
from email.mime.text import MIMEText

# Đường dẫn DB: users.db nằm cùng thư mục
BASE_DIR = os.path.dirname(__file__)
DB_PATH  = os.path.join(BASE_DIR, "users.db")

#  Hàm băm SHA‑256
def sha256_hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

# OTP tạm thời & danh sách xác minh
otp_store = {}       # {msv: (otp_code, timestamp)}
otp_verified = set() # msv đã xác minh otp thành công

#  Gửi OTP qua email
def send_otp_email(to_email: str, otp_code: str) -> bool:
    from_email   = "ragcuatoi123@gmail.com"
    app_password = "cjkp omys opyj mdzc"

    subject = "Mã xác nhận đặt lại mật khẩu"
    body = f"""
Xin chào,

Mã xác nhận để đặt lại mật khẩu của bạn là: {otp_code}
Mã này sẽ hết hạn sau 5 phút. Vui lòng không chia sẻ mã này với bất kỳ ai.

Trân trọng,
RAG TLU
"""

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"]   = to_email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(from_email, app_password)
            server.send_message(msg)
        print("Đã gửi email OTP.")
        return True
    except Exception as e:
        print("Gửi email thất bại:", e)
        return False

# Khởi tạo DB & bảng users
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        student_id INTEGER PRIMARY KEY CHECK(length(student_id) = 10),
        email TEXT UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL
    );
    """)
    conn.commit(); conn.close()
    print("users.db & bảng users sẵn sàng.")

# Kiểm tra email hợp lệ?
def valid_email(email: str) -> bool:
    email = email.strip()
    return re.fullmatch(r"[^@]+@[^@]+\.[^@]+", email) is not None

# Thêm / cập nhật tài khoản
def add_user(student_id: str, email: str, raw_password: str):
    if not valid_email(email):
        print("Email không hợp lệ."); return
    if not student_id.isdigit() or len(student_id) != 10:
        print("MSV phải là số 10 chữ số."); return
    student_id = int(student_id)
    hashed = sha256_hash(raw_password)
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    try:
        cur.execute("""
        INSERT INTO users (student_id, email, hashed_password)
        VALUES (?, ?, ?)
        ON CONFLICT(student_id) DO UPDATE SET
            email = excluded.email,
            hashed_password = excluded.hashed_password;
        """, (student_id, email, hashed))
        conn.commit(); print(f"Đã thêm/cập nhật MSV: {student_id}")
    except sqlite3.IntegrityError:
        print("Email đã tồn tại ở tài khoản khác.")
    finally:
        conn.close()

#  Xác thực đăng nhập
def verify_login(student_id: str, raw_password: str) -> bool:
    if not student_id.isdigit(): return False
    student_id = int(student_id)
    hashed = sha256_hash(raw_password)
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT 1 FROM users
        WHERE student_id = ? AND hashed_password = ?
    """, (student_id, hashed))
    ok = cur.fetchone() is not None
    conn.close(); return ok

# Đổi mật khẩu
def update_password(student_id: str, new_password: str):
    student_id = int(student_id)
    hashed = sha256_hash(new_password)
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        UPDATE users SET hashed_password = ?
        WHERE student_id = ?
    """, (hashed, student_id))
    if cur.rowcount:
        print("Đã đổi mật khẩu.")
    else:
        print("Không tìm thấy MSV.")
    conn.commit(); conn.close()

#  Danh sách user
def list_users():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT student_id, email, hashed_password FROM users")
    rows = cur.fetchall(); conn.close()
    if not rows:
        print("Chưa có tài khoản nào."); return
    print("Danh sách tài khoản:")
    for sid, mail, hpw in rows:
        print(f" • {sid:<10} | {mail:<25} | {hpw[:6]}...")

#  Quên mật khẩu  gửi OTP
def forgot_password(student_id: str) -> bool:
    student_id = int(student_id)
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT email FROM users WHERE student_id=?", (student_id,))
    row = cur.fetchone(); conn.close()
    if not row:
        print("Không tìm thấy MSV."); return False
    email = row[0]
    otp_code = str(random.randint(100000, 999999))
    otp_store[student_id] = (otp_code, time.time())
    print(f"Gửi OTP {otp_code} đến {email}")
    return send_otp_email(email, otp_code)

# Xác minh OTP
def verify_otp(student_id: str, user_input: str) -> bool:
    student_id = int(student_id)
    data = otp_store.get(student_id)
    if not data:
        print("Chưa gửi OTP."); return False
    otp_code, created = data
    if time.time() - created > 300:
        print(" OTP hết hạn."); return False
    if user_input == otp_code:
        otp_verified.add(student_id)
        del otp_store[student_id]
        print("OTP hợp lệ.")
        return True
    print("OTP sai."); return False

#  Đặt lại mật khẩu mới (sau khi OTP đúng)
def reset_password(student_id: str, new_password: str):
    student_id = int(student_id)
    if student_id not in otp_verified:
        print("Chưa xác minh OTP."); return False
    update_password(student_id, new_password)
    otp_verified.discard(student_id)
    print("Đã đặt mật khẩu mới.")
    return True

# 3
if __name__ == "__main__":
    init_db()
    add_user("2151062697", "lehuyenao123@gmail.com", "123456")
    add_user("2151063000", "lehuyenao@gmail.com", "1234563")
    add_user("2151063001", "testlp1@gmail.com", "1234567890")
    add_user("2151063002", "testlp2@gmail.com", "123456789")
    add_user("2151063003", "testlp3@gmail.com", "0123456")
    add_user("2151063004", "testlp4@gmail.com", "1234567")
    add_user("2151062025", "thanhan2k35788@gmail.com", "1234567890")

    for i in range(2151063005, 2151063020):
        msv = str(i)
        email = f"test{i}@gmail.com"
        password = "123456"
        add_user(msv, email, password)

    list_users()
