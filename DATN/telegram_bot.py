from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import os
import re
from io import BytesIO

# Nhập các hàm từ file Gradio gốc
from main import chatbot_interface  # thay 'your_gradio_file' bằng tên file .py bạn đã tạo
from PIL import Image

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # Đặt trong .env hoặc gán trực tiếp

# Lưu student_id theo user_id
student_id_mapping = {}

# async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     await update.message.reply_text("🎓 Chào bạn! Gửi /id <mã sinh viên> để bắt đầu.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🎓 **Chào mừng đến với Trợ lý học tập!**\n\n"
        "Tôi có thể giúp bạn tra cứu điểm, GPA, số tín chỉ, và các thông tin học tập khác.\n\n"
        "🔧 **Cách sử dụng:**\n"
        "1. Gửi lệnh `/id <mã_sinh_viên>` để thiết lập mã sinh viên của bạn. Ví dụ: `/id 2151062697`\n"
        "2. Sau đó, bạn có thể hỏi:\n"
        "   • *GPA học kỳ 1_2024_2025 là bao nhiêu?*\n"
        "   • *Danh sách các môn trong chương trình đào tạo*\n"
        "   • *Tổng số tín chỉ tôi đã tích lũy là bao nhiêu?*\n"
        "   • *Điểm môn Cơ sở dữ liệu?*\n"
        "\n📌 Hãy thử gửi một câu hỏi ngay bây giờ!"
    )
    await update.message.reply_markdown(welcome_text)

async def set_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        student_id = context.args[0]
        if re.match(r"^\d{10}$", student_id):
            student_id_mapping[update.effective_user.id] = student_id
            await update.message.reply_text(f"✅ Đã lưu mã sinh viên: {student_id}")
        else:
            await update.message.reply_text("❌ Mã sinh viên không hợp lệ. Phải đủ 10 chữ số.")
    except:
        await update.message.reply_text("⚠️ Vui lòng dùng đúng cú pháp: /id <mã_sinh_viên>")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in student_id_mapping:
        await update.message.reply_text("⚠️ Bạn chưa đặt mã sinh viên. Gửi: /id <mã_sinh_viên>")
        return

    student_id = student_id_mapping[user_id]
    query = update.message.text
    result_text, result_image = chatbot_interface(query, student_id)

    if result_image:
        # Gửi ảnh từ bộ nhớ RAM thay vì ghi file
        bio = BytesIO()
        result_image.save(bio, format='JPEG')
        bio.name = "hihi.jpg"
        bio.seek(0)
        await update.message.reply_photo(photo=InputFile(bio), caption=result_text or "")
    else:
        await update.message.reply_text(result_text)

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", set_id))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot Telegram đang chạy...")
    app.run_polling()

if __name__ == "__main__":
    main()
