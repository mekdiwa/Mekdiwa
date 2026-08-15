import os
import re
import json
from threading import Thread
from flask import Flask
from telegram import Update, MessageEntity, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ================= ใส่ TELEGRAM TOKEN ตรงนี้ =================
TELEGRAM_TOKEN = "8510442078:AAEQxzafOyI-iuV9ZPhLWQBt3C7w7IlHy2g"
# ==========================================================

DB_BANNED = "banned_users.json"
DB_MEMBERS = "known_members.json"

def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_json(filepath, data):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

banned_users = load_json(DB_BANNED)
known_members = load_json(DB_MEMBERS)  # จำ username -> user_id

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

async def is_user_admin(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator']
    except Exception:
        return False

# --- 1. ข้อความต้อนรับสมาชิกใหม่ ---
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            continue
        
        # บันทึกข้อมูลสมาชิก
        if member.username:
            known_members[member.username.lower()] = {"id": member.id, "name": member.first_name}
            save_json(DB_MEMBERS, known_members)

        user_name = member.first_name
        welcome_text = (
            f"สวัสดีครับคุณ {user_name} ยินดีต้อนรับเข้าสู่กลุ่มครับ! 🎉\n\n"
            f"ผมคือ ADMINBOT-BAN บอทผู้ช่วยดูแลกลุ่ม\n"
            f"ยินดีที่ได้รู้จัก ขอให้พูดคุยกันอย่างสุภาพและทำตามกฎด้วยนะครับ 🛡️"
        )
        await update.message.reply_text(welcome_text)

# --- 2. ตรวจจับข้อความ, บันทึกผู้ใช้, แท็กบอท & ป้องกันลิงก์ ---
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = user.id
    bot_username = (await context.bot.get_me()).username

    # จำ ID ของทุกคนที่พิมพ์ในกลุ่ม
    if user.username:
        known_members[user.username.lower()] = {"id": user_id, "name": user.first_name}
        save_json(DB_MEMBERS, known_members)

    # แท็กบอทเพื่อดูคำสั่ง
    if f"@{bot_username}".lower() in message.text.lower():
        if await is_user_admin(chat_id, user_id, context):
            admin_help_text = (
                "🛡️ **คำสั่งแอดมิน**\n\n"
                "• **แบน:** Reply ข้อความคนนั้น แล้วพิมพ์ `/ban`\n"
                "• **แบนด้วย @/ID:** พิมพ์ `/ban @username` หรือ `/ban <ID>`\n"
                "• **ปลดแบน:** พิมพ์ `/unban <ID>`\n"
                "• **ดูประวัติแบน:** พิมพ์ `/banlist`\n"
                "• **เปิด/ปิดกลุ่ม:** `/open on` หรือ `/open off`\n\n"
                "*(ระบบกันลิงก์และต้อนรับ ทำงานให้อัตโนมัติ)*"
            )
            await message.reply_text(admin_help_text, parse_mode="Markdown")
            return

    # Anti-Link สำหรับสมาชิกทั่วไป
    if not await is_user_admin(chat_id, user_id, context):
        has_link = False
        for entity in message.entities or []:
            if entity.type in [MessageEntity.URL, MessageEntity.TEXT_LINK]:
                has_link = True
                break

        if not has_link:
            url_pattern = r"(https?://\S+|t\.me/\S+|www\.\S+)"
            if re.search(url_pattern, message.text, re.IGNORECASE):
                has_link = True

        if has_link:
            try:
                await message.delete()
                await message.chat.send_message(f"⚠️ ไม่อนุญาตให้ส่งลิงก์ครับคุณ {user.first_name}")
            except Exception:
                pass

# --- 3. คำสั่ง /ban ---
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id
    message = update.message

    if not await is_user_admin(chat_id, sender_id, context):
        await message.reply_text("❌ คุณไม่ใช่แอดมิน ไม่มีสิทธิ์ใช้คำสั่งนี้")
        return

    target_user_id = None
    target_name = ""

    # แบบที่ 1: Reply ข้อความ
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id
        target_name = target_user.first_name

    # แบบที่ 2: Text Mention สีฟ้า
    if not target_user_id:
        for entity in message.entities or []:
            if entity.type == MessageEntity.TEXT_MENTION:
                target_user_id = entity.user.id
                target_name = entity.user.first_name
                break

    # แบบที่ 3: ค้นหาจาก @username ในฐานข้อมูลที่จำไว้
    if not target_user_id:
        mentions = re.findall(r'@([a-zA-Z0-9_]+)', message.text)
        for u in mentions:
            u_clean = u.lower()
            if u_clean in known_members:
                target_user_id = known_members[u_clean]["id"]
                target_name = known_members[u_clean]["name"]
                break

    # แบบที่ 4: ตัวเลข ID
    if not target_user_id:
        numbers = re.findall(r'\d{6,}', message.text)
        if numbers:
            target_user_id = int(numbers[0])
            target_name = f"ID: {target_user_id}"

    # ถ้าหาไม่เจอ
    if not target_user_id:
        await message.reply_text(
            "⚠️ **ไม่พบ ID ของสมาชิกที่จะแบน**\n\n"
            "💡 แนะนำให้ใช้การ **กด Reply ข้อความ** ของคนนั้น แล้วพิมพ์ `/ban` จะแม่นยำและติดทันที 100% ครับ",
            parse_mode="Markdown"
        )
        return

    try:
        await context.bot.ban_chat_member(chat_id, target_user_id)
        banned_users[str(target_user_id)] = target_name
        save_json(DB_BANNED, banned_users)
        await message.reply_text(f"🚀 แบนคุณ **{target_name}** ออกจากกลุ่มเรียบร้อยแล้ว!", parse_mode="Markdown")
    except Exception:
        await message.reply_text("❌ ไม่สามารถแบนได้ (ตรวจสอบว่าบอทมีสิทธิ์แอดมินหรือเป้าหมายเป็นแอดมิน)")

# --- 4. คำสั่ง /unban ---
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id
    message = update.message

    if not await is_user_admin(chat_id, sender_id, context):
        await message.reply_text("❌ คุณไม่ใช่แอดมิน")
        return

    numbers = re.findall(r'\d+', message.text)
    if not numbers:
        await update.message.reply_text("📌 พิมพ์ `/unban` ตามด้วยเลข ID เช่น `/unban 7285731264`")
        return

    target_user_id = int(numbers[0])

    try:
        await context.bot.unban_chat_member(chat_id=chat_id, user_id=target_user_id)
        banned_users.pop(str(target_user_id), None)
        save_json(DB_BANNED, banned_users)
        await update.message.reply_text(f"✅ ปลดแบน ID: `{target_user_id}` เรียบร้อยแล้ว สมาชิกสามารถกดลิงก์กลับเข้ากลุ่มได้ครับ", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("❌ ปลดแบนไม่สำเร็จ")

# --- 5. คำสั่ง /banlist ---
async def banlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id

    if not await is_user_admin(chat_id, sender_id, context):
        return

    if not banned_users:
        await update.message.reply_text("📋 ยังไม่มีประวัติรายชื่อคนที่ถูกแบนในกลุ่มนี้")
        return

    text = "📋 **รายชื่อสมาชิกที่ถูกแบน:**\n"
    for uid, uname in banned_users.items():
        text += f"- {uname} (ID: `{uid}`)\n"
    await update.message.reply_text(text, parse_mode="Markdown")

# --- 6. คำสั่ง /open on / off ---
async def open_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id

    if not await is_user_admin(chat_id, sender_id, context):
        return

    text = update.message.text.lower()
    try:
        if "off" in text:
            await context.bot.set_chat_permissions(chat_id, ChatPermissions(can_send_messages=False))
            await update.message.reply_text("🔒 ปิดกลุ่มเรียบร้อย (สมาชิกทั่วไปพิมพ์ไม่ได้)")
        elif "on" in text:
            perms = ChatPermissions(
                can_send_messages=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
            await context.bot.set_chat_permissions(chat_id, perms)
            await update.message.reply_text("🔓 เปิดกลุ่มเรียบร้อย (สมาชิกทุกคนพิมพ์ได้ตามปกติ)")
        else:
            await update.message.reply_text("📌 พิมพ์ `/open on` เพื่อเปิด หรือ `/open off` เพื่อปิด")
    except Exception:
        await update.message.reply_text("❌ ไม่สามารถตั้งค่ากลุ่มได้")

if __name__ == '__main__':
    bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    bot_app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    bot_app.add_handler(CommandHandler("ban", ban))
    bot_app.add_handler(CommandHandler("unban", unban))
    bot_app.add_handler(CommandHandler("banlist", banlist))
    bot_app.add_handler(CommandHandler("open", open_group))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))

    bot_app.run_polling()
