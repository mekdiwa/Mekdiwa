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

# รายชื่อเก็บบันทึกคนโดนแบนในระบบ
banned_users = {}

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

# เช็กสิทธิ์แอดมิน
async def is_user_admin(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator']
    except Exception:
        return False

# --- 1. ข้อความต้อนรับสมาชิกใหม่ + แนะนำตัว ---
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

# --- 2. ฟังก์ชันตรวจจับการแท็กบอทเพื่อส่งคู่มือคำสั่งแอดมิน ---
async def handle_mentions_and_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username

    # ตรวจว่ามีการแท็กบอทหรือไม่ (@username_bot)
    if f"@{bot_username}".lower() in message.text.lower():
        # ถ้าเป็นแอดมินแท็ก ส่งคู่มือคำสั่งให้
        if await is_user_admin(chat_id, user_id, context):
            admin_help_text = (
                "🛡️ **คำสั่งแอดมิน (Admin Commands)**\n\n"
                "• `/ban` หรือ `/ban @ชื่อ` — แบนสมาชิกออกจากกลุ่ม\n"
                "• `/unban <ID>` — ปลดแบนสมาชิก (ดู ID จาก banlist)\n"
                "• `/banlist` — ดูรายชื่อและ ID คนที่โดนแบน\n"
                "• `/open off` — ปิดกลุ่ม (ห้ามสมาชิกพิมพ์)\n"
                "• `/open on` — เปิดกลุ่ม (ให้สมาชิกพิมพ์ได้ปกติ)\n\n"
                "*(ระบบลบลิงก์และต้อนรับสมาชิกใหม่ทำงานอัตโนมัติ)*"
            )
            await message.reply_text(admin_help_text, parse_mode="Markdown")
            return

    # ระบบป้องกันลิงก์ (Anti-Link) สำหรับสมาชิกทั่วไป
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
                await message.chat.send_message(
                    f"⚠️ ไม่อนุญาตให้ส่งลิงก์ในกลุ่มครับคุณ {update.effective_user.first_name}"
                )
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

    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id
        target_name = target_user.first_name
    else:
        for entity in message.entities or []:
            if entity.type == MessageEntity.TEXT_MENTION:
                target_user_id = entity.user.id
                target_name = entity.user.first_name
                break
        if not target_user_id and context.args:
            arg = context.args[0]
            if arg.isdigit():
                target_user_id = int(arg)
                target_name = f"ID: {target_user_id}"

    if not target_user_id:
        await message.reply_text("📌 วิธีใช้: Reply ข้อความ หรือพิมพ์ `/ban @username` หรือ `/ban <User_ID>`")
        return

    try:
        await context.bot.ban_chat_member(chat_id, target_user_id)
        banned_users[target_user_id] = target_name
        await message.reply_text(f"🚀 แบนคุณ {target_name} ออกจากกลุ่มเรียบร้อยแล้ว!")
    except Exception:
        await message.reply_text("❌ ไม่สามารถแบนได้ (บอทอาจไม่มีสิทธิ์หรือเป้าหมายเป็นแอดมิน)")

# --- 4. คำสั่ง /unban ---
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sender_id = update.effective_user.id

    if not await is_user_admin(chat_id, sender_id, context):
        await message.reply_text("❌ คุณไม่ใช่แอดมิน ไม่มีสิทธิ์ใช้คำสั่งนี้")
        return

    target_user_id = None
    if context.args and context.args[0].isdigit():
        target_user_id = int(context.args[0])

    if not target_user_id:
        await update.message.reply_text("📌 วิธีใช้: พิมพ์ `/unban <User_ID>`")
        return

    try:
        await context.bot.unban_chat_member(chat_id, target_user_id, only_if_banned=True)
        banned_users.pop(target_user_id, None)
        await update.message.reply_text(f"✅ ปลดแบน ID: {target_user_id} เรียบร้อยแล้ว")
    except Exception:
        await update.message.reply_text("❌ ปลดแบนไม่สำเร็จ กรุณาตรวจสอบ ID อีกครั้ง")

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
        await update.message.reply_text("❌ คุณไม่ใช่แอดมิน ไม่มีสิทธิ์ใช้คำสั่งนี้")
        return

    if not context.args or context.args[0].lower() not in ['on', 'off']:
        await update.message.reply_text("📌 วิธีใช้:\n- `/open on` เพื่อเปิดกลุ่ม\n- `/open off` เพื่อปิดกลุ่ม")
        return

    action = context.args[0].lower()
    try:
        if action == 'off':
            perms = ChatPermissions(can_send_messages=False)
            await context.bot.set_chat_permissions(chat_id, perms)
            await update.message.reply_text("🔒 **ปิดกลุ่มเรียบร้อย:** สมาชิกทั่วไปไม่สามารถส่งข้อความได้", parse_mode="Markdown")
        else:
            perms = ChatPermissions(
                can_send_messages=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
            await context.bot.set_chat_permissions(chat_id, perms)
            await update.message.reply_text("🔓 **เปิดกลุ่มเรียบร้อย:** สมาชิกทุกคนสามารถพิมพ์ได้ตามปกติ", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("❌ ไม่สามารถเปลี่ยนสิทธิ์กลุ่มได้ (กรุณาให้สิทธิ์ Change Group Info แก่บอท)")

if __name__ == '__main__':
    bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # ต้อนรับสมาชิกใหม่
    bot_app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))

    # คำสั่งแอดมิน
    bot_app.add_handler(CommandHandler("ban", ban))
    bot_app.add_handler(CommandHandler("unban", unban))
    bot_app.add_handler(CommandHandler("banlist", banlist))
    bot_app.add_handler(CommandHandler("open", open_group))

    # ดักจับการแท็กบอท + กันลิงก์สแปม
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_mentions_and_links))

    bot_app.run_polling()
