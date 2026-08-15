import os
import random
from threading import Thread
from flask import Flask
import google.generativeai as genai
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ================= 1. ใส่ KEY ตรงนี้ =================
TELEGRAM_TOKEN = "8510442078:AAFYfCBK6kT4mASprz_4836FecLq43l3P0E"
GEMINI_API_KEY = "AQ.Ab8RN6IyFZ0LZNhCl2ya0JNqHVf6M8AzLBubjimVpKZmRXlPGQ"
# ===================================================

# --- โค้ด Web Server จำลอง (กันหลับ 24 ชม.) ---
app = Flask(__name__)
@app.route('/')
def home():
    return "ADMINBOT-BAN is Running 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

Thread(target=run_web).start()
# ---------------------------------------------

# ตั้งค่าบุคลิก AI ประจำตัว ADMINBOT-BAN
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction=(
        "คุณคือ 'ADMINBOT-BAN' บอทแอดมินสายโหดแต่โหมดฮาประจำกลุ่ม Telegram "
        "บุคลิกภาพ: เป็นกันเอง กวนประสาทนิดๆ ขี้เล่น ชอบแซวเรื่องแบนแบบขำๆ มีอารมณ์ขัน "
        "กฎเหล็กในการตอบ: "
        "1. ตอบสั้นๆ กระชับ ห้วนๆ เหมือนคนพิมพ์แชทมือถือ (1-2 ประโยคพอ) "
        "2. ห้ามตอบยาวเป็นเรียงความ "
        "3. ห้ามพูดจาทางการ ห้ามมีคำว่า 'สวัสดีครับ มีอะไรให้ช่วยไหม' "
        "4. ใช้คำว่า 55555, ดิวะ, เดี๋ยวปั๊ดแบนเลย ได้ตามฟีลลิ่งเพื่อนแซวกัน"
    )
)

# --- ระบบแชท AI คุยเล่น ---
async def natural_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    bot_username = (await context.bot.get_me()).username
    text = message.text
    
    is_reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id
    is_mentioned = f"@{bot_username}" in text
    random_talk = random.random() < 0.20  # สุ่มตอบแจม 20%

    if is_mentioned or is_reply_to_bot or random_talk:
        clean_text = text.replace(f"@{bot_username}", "").strip()
        if not clean_text and not is_reply_to_bot:
            return

        try:
            prompt = f"เพื่อนในกลุ่มพูดว่า: \"{clean_text or '...'}\" ตอบกลับสั้นๆ สไตล์แอดมินกวนๆ:"
            response = model.generate_content(prompt)
            await message.reply_text(response.text)
        except Exception:
            pass

# --- ข้อความต้อนรับสมาชิกใหม่ ---
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            continue
        await update.message.reply_text(
            f"ยินดีต้อนรับคุณ {member.first_name} เข้ากลุ่มครับ! 🎉\n"
            f"ผม ADMINBOT-BAN ดูแลที่นี่อยู่ คุยเล่นได้แต่อย่าซ่าเดี๋ยวโดนแบนนะ 555"
        )

# --- คำสั่งแอดมิน /ban ---
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("กด Reply ข้อความคนที่จะให้แบนด้วยนะ")
        return
    user_to_ban = update.message.reply_to_message.from_user
    await context.bot.ban_chat_member(update.effective_chat.id, user_to_ban.id)
    await update.message.reply_text(f"ADMINBOT-BAN จัดการส่งคุณ {user_to_ban.first_name} บินเรียบร้อย! 🚀")

# --- คำสั่งแอดมิน /del ---
async def delete_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        await update.message.reply_to_message.delete()
        await update.message.delete()

if __name__ == '__main__':
    bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    bot_app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    bot_app.add_handler(CommandHandler("ban", ban))
    bot_app.add_handler(CommandHandler("del", delete_msg))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, natural_chat))
    
    bot_app.run_polling()
