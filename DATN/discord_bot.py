import os, discord
import io
from discord.ext import commands
from dotenv import load_dotenv
# from test2 import chatbot_interface
from main import chatbot_interface
from verify_login import (verify_login, forgot_password,verify_otp, reset_password )

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

sessions    = {}  # discord_user_id -> msv
otp_pending = {}  # discord_user_id -> msv đang chờ xác minh OTP
thread_map  = {}  # discord_user_id -> thread_id riêng
context_map = {}
context_prev_question = {}  # discord_user_id -> câu hỏi gần nhất
context_prev_answer = {}  # discord_user_id -> câu trả lời gần nhất

@bot.tree.command(name="start", description="Chào mừng và hướng dẫn sử dụng")
async def start(inter: discord.Interaction):
    welcome = (
        " **Chào mừng bạn đến với Trợ lý tra cứu kết quả học tập cho SV CNTT-TLU!**\n\n"
        "Tôi có thể giúp bạn tra cứu điểm, GPA, số tín chỉ, và các thông tin học tập khác.\n\n"
        " **Hướng dẫn sử dụng:**\n"
        "1. `/dangnhap <msv> <matkhau>` để đăng nhập bằng mã sinh viên và mật khẩu.\n"
        "2. `/chat` để mở thread riêng tư và bắt đầu hỏi đáp.\n"
        "3. Trong thread, gửi câu hỏi như:\n"
        "   • Thông tin môn 'Tiếng Anh 2' của trường mình\n"
        "   • GPA học kỳ 1_2024_2025 là bao nhiêu?\n"
        "   • Điểm môn Cơ sở dữ liệu?\n"
        "   • Kì tới tôi học thêm/học lại môn XXX ,X tín chỉ, được điểm A/B/C/D/F , tính gpa mới?\n\n"
        " **Hướng dẫn khi bạn quên mật khẩu:**\n"
        "1. `/quenmk <msv>` để yêu cầu mã OTP qua email.\n"
        "2. `/maotp <mã>` để xác minh mã OTP.\n"
        "3. `/doimk <matkhau_moi>` để đặt mật khẩu mới sau khi xác minh.\n\n"
        " **Lưu ý:** Bạn cần đăng nhập trước khi sử dụng `/chat`."
        "Hiện tại hệ thống chưa thể cung cấp đầy đủ thông tin về các môn học và số tín chỉ còn thiếu của bạn.\n"
        "Nếu có các câu hỏi liên quan xin hãy dùng lệnh /cntttlu để so sánh. Mong bạn thông cảm vì sự bất tiện này. Xin cảm ơn!"
    )
    await inter.response.send_message(welcome, ephemeral=True)

# /dangnhap
@bot.tree.command(name="dangnhap", description="Đăng nhập: /dangnhap <msv> <matkhau>")
async def dangnhap(inter: discord.Interaction, msv: str, matkhau: str):
    if verify_login(msv, matkhau):
        sessions[inter.user.id] = msv
        await inter.response.send_message("Đăng nhập thành công.", ephemeral=True)
    else:
        await inter.response.send_message("MSV hoặc mật khẩu sai.", ephemeral=True)

# /quenmk msv  – gửi OTP
@bot.tree.command(name="quenmk", description="Gửi mã OTP qua email để đặt lại mật khẩu")
async def quenmk(inter: discord.Interaction, msv: str):
    await inter.response.defer(ephemeral=True)  # giữ kết nối
    if forgot_password(msv):
        otp_pending[inter.user.id] = msv
        await inter.followup.send("Đã gửi mã OTP. Dùng `/maotp <mã>` để xác minh.")
    else:
        await inter.followup.send("Không tìm thấy MSV.")

#  /maotp code – xác minh OTP
@bot.tree.command(name="maotp", description="Xác minh mã OTP")
async def maotp(inter: discord.Interaction, code: str):
    msv = otp_pending.get(inter.user.id)
    if not msv:
        await inter.response.send_message("Bạn chưa yêu cầu OTP.", ephemeral=True)
        return
    if verify_otp(msv, code):
        sessions[inter.user.id] = msv
        otp_pending.pop(inter.user.id, None)
        await inter.response.send_message("OTP đúng. Dùng `/doimk <mới>` để đổi mật khẩu.",ephemeral=True)
    else:
        await inter.response.send_message("Mã OTP sai hoặc đã hết hạn.", ephemeral=True)

# /doimk mật khẩu mới – đặt lại
@bot.tree.command(name="doimk", description="Đặt mật khẩu mới sau khi xác minh OTP")
async def doimk(inter: discord.Interaction, matkhau_moi: str):
    msv = sessions.get(inter.user.id)
    if not msv:
        await inter.response.send_message("Bạn chưa xác minh OTP.", ephemeral=True)
        return
    if reset_password(msv, matkhau_moi):
        await inter.response.send_message("Đổi mật khẩu thành công. Dùng `/dangnhap` để đăng nhập lại.",ephemeral=True)
        sessions.pop(inter.user.id, None)
    else:
        await inter.response.send_message("Không đổi được mật khẩu.", ephemeral=True)

#  /chat – tạo thread riêng tư với bot
@bot.tree.command(name="chat", description="Mở thread riêng để hỏi bot (riêng tư)")
async def chat(inter: discord.Interaction):
    user = inter.user
    msv = sessions.get(user.id)
    if not msv:
        await inter.response.send_message("Bạn cần `/dangnhap` trước.", ephemeral=True)
        return

    thread_id = thread_map.get(user.id)
    thread = bot.get_channel(thread_id) if thread_id else None

    # Tạo nếu chưa có
    if not thread or not isinstance(thread, discord.Thread):
        parent = inter.channel
        thread = await parent.create_thread(
            name=f"Trao đổi {msv}",
            type=discord.ChannelType.private_thread,  #Thread riêng
            invitable=False
        )
        await thread.add_user(user)  #THÊM người dùng vào thread
        thread_map[user.id] = thread.id

    await inter.response.send_message(
        f"Đã mở thread riêng: {thread.mention}",
        ephemeral=True
    )

@bot.tree.command(name="cntttlu", description="Ảnh chương trình đào tạo CNTT TLU theo năm học")
async def cntttlu(inter: discord.Interaction):
    image_path = "tlu.jpg"
    if os.path.exists(image_path):
        await inter.response.send_message(
            content=(
                "Xin chào! Đây là ảnh chương trình đào tạo CNTT của TLU, trong đó có danh sách các môn học.\n\n"
                "Hiện tại tôi chưa thể cung cấp đầy đủ thông tin về các môn học và số tín chỉ còn thiếu."
                "Bạn có thể nhìn ảnh dưới đây để tham khảo cũng như so sánh với tình trạng học tập của bạn.\n\n"
                "Chúng tôi mong rằng trong các phiên bản tiếp theo, hệ thống sẽ hỗ trợ tra cứu chính xác và đầy đủ hơn cho bạn!"
            ),
            file=discord.File(image_path),
            ephemeral=False  #công khai
        )
    else:
        await inter.response.send_message("Không tìm thấy ảnh.", ephemeral=False)


@bot.event
async def on_message(msg: discord.Message):
    if msg.author == bot.user:
        return

    if isinstance(msg.channel, discord.Thread):
        if msg.channel.id in thread_map.values():
            msv = sessions.get(msg.author.id)
            if not msv:
                await msg.channel.send("🔐 Bạn chưa đăng nhập.")
                return

            prev_subject = context_map.get(msg.author.id, "")
            prev_q = context_prev_question.get(msg.author.id, "")
            prev_a = context_prev_answer.get(msg.author.id, "")

            # Gọi chatbot
            reply, new_subject, new_q, new_a = chatbot_interface(msg.content, msv, prev_subject, prev_q, prev_a)

            # Cập nhật lại context
            context_map[msg.author.id] = new_subject
            context_prev_question[msg.author.id] = new_q
            context_prev_answer[msg.author.id] = new_a

            # Trả lời nếu quá dài
            if isinstance(reply, str) and len(reply) > 2000:
                buffer = io.StringIO(reply)
                buffer.seek(0)
                await msg.channel.send(
                    "Nội dung quá dài, mình gửi file đính kèm nhé:",
                    file=discord.File(fp=buffer, filename="tra_loi_bot.txt")
                )
                return

            # Trả lời bình thường
            await msg.channel.send(reply)
            return
    await bot.process_commands(msg)


#  Khởi động bot
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot đã chạy: {bot.user}")

bot.run(TOKEN)
