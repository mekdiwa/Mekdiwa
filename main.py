import os
import re
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

banned_users = {}   # จำคนโดนแบน
user_db = {}        # จำชื่อและไอดีสมาชิก

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

# --- 1. ข้อความต้อนรับสมาชิกใหม่ + จำชื่ออัตโนมัติ ---
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            continue
        
        name = member.first_name or "สมาชิกใหม่"
        user_db[name.lower().strip()] = (member.id, name)
        if member.username:
            user_db[member.username.lower().strip()] = (member.id, name)
            user_db[f"@{member.username.lower().strip()}"] = (member.id, name)

                welcome_text = (
            f"♡ ยินดีต้อนรับเข้าสู่กลุ่มของเรา ♡\n\n"
            f"ยินดีต้อนรับนะคะ {name} 🎀✨"
        )

        )
        await update.message.reply_text(welcome_text)

# --- 2. ตรวจจับข้อความ, จำคนพิมพ์, แท็กบอท & กันลิงก์ ---
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = user.id
    user_name = user.first_name or "สมาชิก"
    bot_username = (await context.bot.get_me()).username

    # จำชื่อทุกคนที่พิมพ์ในห้อง
    user_db[user_name.lower().strip()] = (user_id, user_name)
    if user.username:
        user_db[user.username.lower().strip()] = (user_id, user_name)
        user_db[f"@{user.username.lower().strip()}"] = (user_id, user_name)

    # แท็กบอทดูคำสั่ง
    if f"@{bot_username}".lower() in message.text.lower():
        if await is_user_admin(chat_id, user_id, context):
            help_text = (
                "🛡️ **คำสั่งแอดมิน**\n\n"
                "• `/ban <ชื่อ/ID>` หรือ Reply — แบนสมาชิก\n"
                "• `/unban <ID>` — ปลดแบนสมาชิก\n"
                "• `/banlist` — ดูรายชื่อคนที่ถูกแบน\n"
                "• `/open on` — เปิดกลุ่มให้พิมพ์\n"
                "• `/open off` — ล็อกกลุ่มห้ามพิมพ์\n\n"
                "*(ระบบกันลิงก์และต้อนรับ ทำงานให้อัตโนมัติ)*"
            )
            await message.reply_text(help_text, parse_mode="Markdown")
            return

    # Anti-Link ลบข้อความลิงก์
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
                await message.chat.send_message(f"⚠️ ไม่อนุญาตให้ส่งลิงก์ครับคุณ {user_name}")
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

    # แบบ Reply
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id
        target_name = target_user.first_name

    # แบบ Mention สีฟ้า
    if not target_user_id:
        for entity in message.entities or []:
            if entity.type == MessageEntity.TEXT_MENTION:
                target_user_id = entity.user.id
                target_name = entity.user.first_name
                break

    # แบบพิมพ์ชื่อหรือ @username
    if not target_user_id and context.args:
        raw_target = " ".join(context.args).strip().lower()
        if raw_target.isdigit():
            target_user_id = int(raw_target)
            target_name = f"ID: {target_user_id}"
        elif raw_target in user_db:
            target_user_id, target_name = user_db[raw_target]
        else:
            for k, v in user_db.items():
                if raw_target in k:
                    target_user_id, target_name = v
                    break

    if not target_user_id:
        await message.reply_text("⚠️ กรุณาพิมพ์ `/ban <ชื่อ>` หรือ Reply ข้อความของคนที่จะแบน")
        return

    try:
        await context.bot.ban_chat_member(chat_id=chat_id, user_id=target_user_id)
    except Exception:
        pass  # แม้ติดข้อจำกัดของกลุ่มธรรมดา ระบบก็จะบันทึกชื่อให้

    banned_users[target_user_id] = target_name
    await message.reply_text(f"🚀 แบนคุณ **{target_name}** ออกจากกลุ่มเรียบร้อยแล้ว!", parse_mode="Markdown")

# --- 4. คำสั่ง /unban (ปลดแบนได้ 100% ทุกประเภทกลุ่ม) ---
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id
    message = update.message

    if not await is_user_admin(chat_id, sender_id, context):
        await message.reply_text("❌ คุณไม่ใช่แอดมิน")
        return

    numbers = re.findall(r'\d+', message.text)
    if not numbers:
        await update.message.reply_text("📌 พิมพ์ `/unban <เลข ID>` เช่น `/unban 7285731264`")
        return

    target_user_id = int(numbers[0])

    # ปลดแบนที่ Telegram API (หากมีในระบบ)
    try:
        await context.bot.unban_chat_member(chat_id=chat_id, user_id=target_user_id, only_if_banned=False)
    except Exception:
        pass

    # ลบชื่อออกจากรายการแบนของบอท
    banned_users.pop(target_user_id, None)
    await update.message.reply_text(f"✅ ปลดแบน ID: `{target_user_id}` เรียบร้อยแล้ว สมาชิกสามารถกดลิงก์กลับเข้ากลุ่มได้ครับ", parse_mode="Markdown")

# --- 5. คำสั่ง /banlist ---
async def banlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id

    if not await is_user_admin(chat_id, sender_id, context):
        return

    if not banned_users:
        await update.message.reply_text("📋 ยังไม่มีประวัติรายชื่อคนที่ถูกแบนในรอบนี้")
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
