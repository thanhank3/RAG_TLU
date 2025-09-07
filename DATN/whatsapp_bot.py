from flask import Flask, request
from main import chatbot_interface  # Gọi vào hàm chính của bạn

from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

# Giả sử lưu student_id tạm, bạn có thể mở rộng thêm
student_id_mapping = {}

@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    user_number = request.form.get("From")  # số WhatsApp người dùng
    message_body = request.form.get("Body")  # nội dung tin nhắn

    # Tạo mã sinh viên nếu người dùng nhập lệnh /id
    if message_body.strip().lower().startswith("/id"):
        parts = message_body.strip().split()
        if len(parts) == 2 and parts[1].isdigit():
            student_id_mapping[user_number] = parts[1]
            resp = MessagingResponse()
            resp.message(f"✅ Đã lưu mã sinh viên: {parts[1]}")
            return str(resp)
        else:
            resp = MessagingResponse()
            resp.message("❌ Vui lòng dùng cú pháp đúng: /id <mã_sinh_viên>")
            return str(resp)

    if user_number not in student_id_mapping:
        resp = MessagingResponse()
        resp.message("⚠️ Bạn chưa thiết lập mã sinh viên. Gửi: /id <mã_sinh_viên>")
        return str(resp)

    # Gọi vào chatbot của bạn
    student_id = student_id_mapping[user_number]
    result_text, _ = chatbot_interface(message_body, student_id)

    # Gửi kết quả trả về WhatsApp
    resp = MessagingResponse()
    resp.message(result_text)
    return str(resp)

if __name__ == "__main__":
    app.run(port=5000)
