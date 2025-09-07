import sqlite3
import hashlib
import os
import re

def init_db():
    """Khởi tạo cơ sở dữ liệu SQLite cho thông tin đăng nhập."""
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            msv TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def hash_password(password):
    """Băm mật khẩu bằng SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def add_user(msv, password):
    """Thêm người dùng mới vào cơ sở dữ liệu."""
    if not re.match(r"^\d{10}$", msv):
        return False, "Mã sinh viên phải là 10 chữ số."
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    password_hash = hash_password(password)
    try:
        cursor.execute("INSERT INTO users (msv, password_hash) VALUES (?, ?)", (msv, password_hash))
        conn.commit()
        conn.close()
        return True, f"Thêm MSV {msv} thành công."
    except sqlite3.IntegrityError:
        conn.close()
        return False, f"MSV {msv} đã tồn tại."

def check_login(msv, password):
    """Kiểm tra thông tin đăng nhập."""
    if not re.match(r"^\d{10}$", msv):
        return False, "Mã sinh viên phải là 10 chữ số."
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    password_hash = hash_password(password)
    cursor.execute("SELECT * FROM users WHERE msv = ? AND password_hash = ?", (msv, password_hash))
    user = cursor.fetchone()
    conn.close()
    if user:
        return True, f"Đăng nhập thành công với MSV: {msv}."
    return False, "MSV hoặc mật khẩu không đúng."

# Khởi tạo DB và thêm người dùng mẫu
if not os.path.exists("users.db"):
    init_db()
    success, message = add_user("2151062697", "password123")
    print(message)
    success, message = add_user("2151063000", "securepass")
    print(message)