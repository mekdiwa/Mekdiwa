import sqlite3
import re
import os
import threading
from flask import Flask
from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from telegram.constants import ChatMemberStatus

# ================= 1. Flask Web Server (สำหรับ Render) =================
server = Flask(__name__)

@server.route('/')
def home():
    return "Bot is running 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    server.run(host="0.0.0.0", port=port)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

# ================= 2. โครงสร้างฐานข้อมูล SQLite =================
DB_NAME = "group_bot.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # ตารางเก็บสมาชิกที่ถูกแบน
    c.execute('''CREATE TABLE IF NOT EXISTS banned_users (
                    chat_id INTEGER,
                    user_id INTEGER,
                    user_tag TEXT,
                    PRIMARY KEY (chat_id, user_id)
                )''')
    # ตารางจำ username กับ user_id
    c.execute('''CREATE TABLE IF NOT EXISTS user_cache (
                    username TEXT PRIMARY KEY,
                    user_id INTEGER
                )''')
    # ตารางเก็บสถานะ (antilink และ group_open)
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
                    chat_id INTEGER PRIMARY KEY,
                    antilink INTEGER DEFAULT 0,
                    group_open INTEGER DEFAULT 1
                )''')
    conn.commit()
    conn.close()

def cache_user(username: str, user_id: int):
    if not username:
        return
    clean_username = username.lstrip("@").lower()
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO user_cache VALUES (?, ?)", (clean_username, user_id))
    conn.commit()
    conn.close()

def get_user_id_by_username(username: str):
    clean_username = username.lstrip("@").lower()
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT user_id FROM user_cache WHERE username = ?", (clean_username,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def is_user_banned(chat_id: int, user_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT 1 FROM banned_users WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    result = c.fetchone()
    conn.close()
    return result is not None

def add_ban(chat_id: int, user_id: int, user_tag: str):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO banned_users VALUES (?, ?, ?)", (chat_id, user_id, user_tag))
    conn.commit()
    conn.close()

def remove_ban(chat_id: int, user_id: int):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM banned_users WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    conn.commit()
    conn.close()

def get_banlist(chat_id: int):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT user_id, user_tag FROM banned_users WHERE chat_id = ?", (chat_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def set_setting(chat_id: int, column: str, value: int):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(f'''INSERT INTO settings (chat_id, {column}) VALUES (?, ?)
                 ON CONFLICT(chat_id) DO UPDATE SET {column}=?''', (chat_id, value, value))
    conn.commit()
    conn.close()

def get_setting(chat_id: int, column: str, default=0) -> int:
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute(f"SELECT {column} FROM settings WHERE chat_id = ?", (chat_id,))
        row = c.fetchone()
        conn.close()
        return row[0] if row is not None else default
    except Exception:
        conn.close()
        return default

# ================= 3. ฟังก์ชันเช็กสิทธิ์แอดมิน =================
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception:
        return False

# ================= ข้อความคู่มือการใช้งาน =================
HELP_TEXT = """📖 **คู่มือคำสั่งการใช้งานบอท:**

🔒 **ระบบเปิด/ปิดแชตในกลุ่ม:**
• `/open on` — เปิดกลุ่ม ให้สมาชิกทุกคนพิมพ์คุยได้
• `/open off` — ปิดกลุ่ม สมาชิกทั่วไปจะพิมพ์ไม่ได้ (แอดมินพิมพ์ได้ปกติ)

🛡️ **ระบบป้องกันลิงก์:**
• `/antilink on` — เปิดระบบลบข้อความที่มีลิงก์อัตโนมัติ
• `/antilink off` — ปิดระบบป้องกันลิงก์

🚫 **ระบบแบนสมาชิก (เข้ากลุ่มผ่านลิงก์ไม่ได้อีก):**
• `/ban @username` — สั่งแบนด้วยการแท็กชื่อ
• `/ban <User_ID>` — สั่งแบนด้วย User ID
• *หรือ Reply ข้อความของคนที่ต้องการ แล้วพิมพ์ `/ban`*

✅ **ระบบปลดแบน:**
• `/unban @username` — ปลดแบนด้วยชื่อ
• `/unban <User_ID>` — ปลดแบนด้วย User ID

📋 **ดูรายชื่อคนโดนแบน:**
• `/banlist` — แสดงรายชื่อผู้ถูกแบนทั้งหมดในกลุ่ม"""

# ================= 4. คำสั่งจัดการเปิด/ปิดแชตกลุ่ม =================
async def open_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return

    chat_id = update.effective_chat.id
    if not context.args or context.args[0].lower() not in ["on", "off"]:
        await update.message.reply_text("⚠️ กรุณาระบุคำสั่ง:\n• `/open on` = เปิดกลุ่มให้ทุกคนพิมพ์คุยได้\n• `/open off` = ปิดกลุ่ม สมาชิกทั่วไปจะพิมพ์ไม่ได้", parse_mode="Markdown")
        return

    mode = context.args[0].lower()

    if mode == "off":
        permissions = ChatPermissions(
            can_send_messages=False,
            can_send_audios=False,
            can_send_documents=False,
            can_send_photos=False,
            can_send_videos=False,
            can_send_video_notes=False,
            can_send_voice_notes=False,
            can_send_polls=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False
        )
        try:
            await context.bot.set_chat_permissions(chat_id, permissions)
        except Exception:
            pass
        set_setting(chat_id, "group_open", 0)
        await update.message.reply_text("🔒 **ปิดกลุ่มเรียบร้อยแล้ว**\nสมาชิกทั่วไปจะไม่สามารถส่งข้อความได้ (แอดมินส่งได้ปกติ)", parse_mode="Markdown")

    elif mode == "on":
        permissions = ChatPermissions(
            can_send_messages=True,
            can_send_audios=True,
            can_send_documents=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_video_notes=True,
            can_send_voice_notes=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_invite_users=True
        )
        try:
            await context.bot.set_chat_permissions(chat_id, permissions)
        except Exception:
            pass
        set_setting(chat_id, "group_open", 1)
        await update.message.reply_text("🔓 **เปิดกลุ่มเรียบร้อยแล้ว**\nสมาชิกทุกคนสามารถพิมพ์สนทนาได้ตามปกติ", parse_mode="Markdown")

# ================= 5. คำสั่งระบบป้องกันลิงก์ =================
async def antilink_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return

    chat_id = update.effective_chat.id
    if not context.args or context.args[0].lower() not in ["on", "off"]:
        await update.message.reply_text("⚠️ กรุณาระบุคำสั่ง:\n• `/antilink on` = เปิดระบบลบข้อความที่มีลิงก์\n• `/antilink off` = ปิดระบบกันลิงก์", parse_mode="Markdown")
        return

    mode = context.args[0].lower()
    if mode == "on":
        set_setting(chat_id, "antilink", 1)
        await update.message.reply_text("🛡️ **เปิดระบบป้องกันลิงก์แล้ว**\nข้อความที่มีลิงก์จากสมาชิกทั่วไปจะถูกลบทันที", parse_mode="Markdown")
    else:
        set_setting(chat_id, "antilink", 0)
        await update.message.reply_text("🔓 **ปิดระบบป้องกันลิงก์แล้ว**", parse_mode="Markdown")

# ================= 6. คำสั่งแบน / ปลดแบน / Banlist =================
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return

    chat_id = update.effective_chat.id
    target_id = None
    target_tag = ""

    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_id = target_user.id
        target_tag = f"@{target_user.username}" if target_user.username else f"ID: {target_id}"
    elif context.args:
        arg = context.args[0]
        if update.message.entities:
            for entity in update.message.entities:
                if entity.type == "text_mention":
                    target_id = entity.user.id
                    target_tag = f"ID: {target_id}"
                    break
        if not target_id:
            if arg.startswith("@"):
                cached_id = get_user_id_by_username(arg)
                if cached_id:
                    target_id = cached_id
                    target_tag = arg
                else:
                    await update.message.reply_text(f"⚠️ บอทยังไม่เคยเห็น {arg} ในกลุ่ม กรุณา Reply ข้อความของเขาเพื่อแบน", parse_mode="Markdown")
                    return
            elif arg.isdigit():
                target_id = int(arg)
                target_tag = f"ID: `{target_id}`"

    if not target_id:
        await update.message.reply_text("⚠️ กรุณาระบุชื่อ เช่น `/ban @username` หรือ Reply ข้อความคนที่ต้องการแบน", parse_mode="Markdown")
        return

    try:
        await context.bot.ban_chat_member(chat_id, target_id)
        add_ban(chat_id, target_id, target_tag)
        await update.message.reply_text(f"🚫 แบนผู้ใช้ {target_tag} เรียบร้อยแล้ว (ไม่สามารถเข้ากลุ่มผ่านลิงก์ได้อีก)")
    except Exception as e:
        await update.message.reply_text(f"❌ ไม่สามารถแบนได้: {e}")

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return

    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("⚠️ กรุณาระบุ เช่น `/unban @username` หรือ `/unban 123456789`", parse_mode="Markdown")
        return

    arg = context.args[0]
    target_id = None

    if arg.startswith("@"):
        target_id = get_user_id_by_username(arg)
        if not target_id:
            for uid, tag in get_banlist(chat_id):
                if tag.lower() == arg.lower():
                    target_id = uid
                    break
    elif arg.isdigit():
        target_id = int(arg)

    if not target_id:
        await update.message.reply_text("⚠️ ไม่พบผู้ใช้นี้ในระบบ กรุณาใช้คำสั่ง `/banlist` เพื่อดู ID แล้วปลดแบนด้วย ID แทน", parse_mode="Markdown")
        return

    try:
        try:
            await context.bot.unban_chat_member(chat_id, target_id, only_if_banned=True)
        except Exception:
            pass
        remove_ban(chat_id, target_id)
        await update.message.reply_text(f"✅ ปลดแบนผู้ใช้ {arg} (ID: `{target_id}`) เรียบร้อยแล้ว สามารถกดเข้ากลุ่มได้ตามปกติ", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ ไม่สามารถปลดแบนได้: {e}")

async def banlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return

    chat_id = update.effective_chat.id
    banned_list = get_banlist(chat_id)

    if not banned_list:
        await update.message.reply_text("📋 ไม่มีรายชื่อผู้ถูกแบนในกลุ่มนี้")
        return

    msg = "📋 **รายชื่อผู้ถูกแบนทั้งหมด:**\n\n"
    for idx, (uid, tag) in enumerate(banned_list, 1):
        msg += f"{idx}. {tag} — (ID: `{uid}`)\n"

    await update.message.reply_text(msg, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")

# ================= 7. ตรวจจับข้อความ, แท็กบอท, ลบข้อความตอนปิดกลุ่ม, และดักลิงก์ =================
LINK_REGEX = re.compile(r'(https?://\S+|www\.\S+|t\.me/\S+)', re.IGNORECASE)

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.from_user:
        return

    user = update.message.from_user
    chat_id = update.effective_chat.id
    text = update.message.text or update.message.caption or ""

    if user.username:
        cache_user(user.username, user.id)

    # 1. ตรวจสอบว่ามีการ "แท็กชื่อบอท" หรือไม่ -> ถ้าแท็กให้ตอบคู่มือการใช้งาน
    bot_username = context.bot.username
    if bot_username:
        is_bot_tagged = False
        if f"@{bot_username.lower()}" in text.lower():
            is_bot_tagged = True
        elif update.message.entities:
            for entity in update.message.entities:
                if entity.type == "mention":
                    mention_text = text[entity.offset:entity.offset + entity.length]
                    if mention_text.lower() == f"@{bot_username.lower()}":
                        is_bot_tagged = True
                        break
        
        if is_bot_tagged:
            await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")
            return

    # 2. ตรวจสอบสิทธิ์ถ้าไม่ใช่แอดมิน
    if not await is_admin(update, context):
        # 2.1 เช็กระบบปิดกลุ่ม (ถ้าปิดกลุ่มอยู่ ให้ลบข้อความทันที)
        if get_setting(chat_id, "group_open", default=1) == 0:
            try:
                await update.message.delete()
                return
            except Exception:
                pass

        # 2.2 เช็กระบบป้องกันลิงก์
        if get_setting(chat_id, "antilink", default=0) == 1:
            has_link = bool(LINK_REGEX.search(text))
            if not has_link and update.message.entities:
                for entity in update.message.entities:
                    if entity.type in ["url", "text_link"]:
                        has_link = True
                        break
            
            if has_link:
                try:
                    await update.message.delete()
                except Exception:
                    pass

# ================= 8. ต้อนรับสมาชิกใหม่ + ป้องกันคนโดนแบน =================
async def greet_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            continue

        chat_id = update.effective_chat.id
        
        if member.username:
            cache_user(member.username, member.id)

        if is_user_banned(chat_id, member.id):
            try:
                await context.bot.ban_chat_member(chat_id, member.id)
                continue
            except Exception:
                pass

        user_mention = member.mention_html()
        welcome_text = f"♡ ยินดีต้อนรับเข้าสู่กลุ่มของเรา ♡\n{user_mention}"
        await update.message.reply_text(welcome_text, parse_mode="HTML")

# ================= 9. เริ่มต้นการทำงาน =================
def main():
    init_db()
    keep_alive()  # รัน Web Server หลอก Render
    
    # 🔴 นำ Token ที่ได้จาก @BotFather มาวางตรงนี้
    BOT_TOKEN = "8510442078:AAEuWv8BiGC_skVYM5xDYvlGhdH9RwyBg3c"

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # ลงทะเบียนคำสั่ง
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("start", help_command))
    app.add_handler(CommandHandler("open", open_command))
    app.add_handler(CommandHandler("antilink", antilink_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("banlist", banlist_command))

    # Event ดักจับ
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, greet_new_member))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_messages))

    print("บอทเริ่มทำงานเรียบร้อย...")
    app.run_polling(drop_pending_updates=True, close_loop=False)

if __name__ == "__main__":
    main()
