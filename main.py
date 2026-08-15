import os
from threading import Thread
from flask import Flask
from telegram import Update, MessageEntity
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ================= ใส่ TELEGRAM TOKEN ตรงนี้ =================
TELEGRAM_TOKEN = "8510442078:AAEQxzafOyI-iuV9ZPhLWQBt3C7w7IlHy2g"
# ==========================================================

# --- Web Server จำลองรัน 24 ชม. ---
app = Flask(__name__)
@app.route('/')
def home():
    return "ADMINBOT-BAN is Running 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

Thread(target=run_web).start()
# ---------------------------------

# --- 1. ต้อนรับสมาชิกใหม่ + แนะนำตัวเอง ---
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            continue
        
        user_name = member.first_name
        welcome_text = (
            f"สวัสดีครับคุณ {user_name} ยินดีต้อนรับเข้าสู่กลุ่มครับ! 🎉\n\n"
            f"ผมคือ ADMINBOT-BAN บอทผู้ช่วยดูแลความสงบเรียบร้อยในกลุ่มนี้\n"
            f"ยินดีที่ได้รู้จัก ขอให้พูดคุยกันอย่างเป็นกันเองและทำตามกฎของกลุ่มด้วยนะครับ 🛡️"
        )
        await update.message.reply_text(welcome_text)

# --- ตรวจสอบสิทธิ์แอดมิน ---
async def is_user_admin(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator']
    except Exception:
        return False

# --- 2. คำสั่งแบนด้วยการแท็กชื่อ (/ban @username หรือ /ban ID) ---
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id
    message = update.message

    # เช็กว่าคนสั่งเป็นแอดมินไหม
    if not await is_user_admin(chat_id, sender_id, context):
        await message.reply_text("❌ คุณไม่ใช่แอดมิน ไม่มีสิทธิ์ใช้คำสั่งนี้")
        return

    target_user_id = None
    target_name = ""

    # ดึง User จากการแท็กชื่อ (Text Mention เช่น คนที่ไม่มี Username แต่ถูกแท็กชื่อ)
    for entity in message.entities or []:
        if entity.type == MessageEntity.TEXT_MENTION:
            target_user_id = entity.user.id
            target_name = entity.user.first_name
            break

    # ดึง User จากการพิมพ์ตัวเลข User ID
    if not target_user_id and context.args:
        first_arg = context.args[0]
        if first_arg.isdigit():
            target_user_id = int(first_arg)
            target_name = f"ID: {target_user_id}"

    # ถ้าหาเป้าหมายไม่เจอ
    if not target_user_id:
        await message.reply_text("📌 วิธีใช้: พิมพ์ `/ban` แล้วเคาะวรรคแท็กชื่อคนที่ต้องการแบน เช่น `/ban @username`")
        return

    # ทำการแบนทันที
    try:
        await context.bot.ban_chat_member(chat_id, target_user_id)
        await message.reply_text(f"🚀 จัดการแบนคุณ {target_name} ออกจากกลุ่มเรียบร้อยแล้ว!")
    except Exception:
        await message.reply_text("❌ ไม่สามารถแบนได้ (กรุณาตรวจสอบว่าบอทมีสิทธิ์แอดมิน หรือเป้าหมายเป็นแอดมิน)")

if __name__ == '__main__':
    bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # ดักจับสมาชิกใหม่
    bot_app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    
    # คำสั่งแบน
    bot_app.add_handler(CommandHandler("ban", ban))
    
    bot_app.run_polling()
