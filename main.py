import sqlite3
import re
import os
import threading
from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from telegram.constants import ChatMemberStatus

# ================= 1. Flask Web Server (สำหรับให้ Render ตรวจจับ Port) =================
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
    # ตารางเก็บคนโดนแบน
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
    # ตารางเก็บสถานะเปิด/ปิดกันลิงก์
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
                    chat_id INTEGER PRIMARY KEY,
                    antilink INTEGER DEFAULT 0
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

def set_antilink(chat_id: int, status: int):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (chat_id, antilink) VALUES (?, ?)", (chat_id, status))
    conn.commit()
    conn.close()

def get_antilink(chat_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT antilink FROM settings WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    conn.close()
    return bool(row[0]) if row else False

# ================= 3. ฟังก์ชันเช็กสิทธิ์แอดมิน =================
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    member = await context.bot.get_chat_member(chat_id, user_id)
    return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]

# ================= 4. คำสั่งจัดการสมาชิกและระบบ =================

# คำสั่ง /ban (พิมพ์ /ban @username หรือ /ban ID หรือ Reply ข้อความ)
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return

    chat_id = update.effective_chat.id
    target_id = None
    target_tag = ""

    # 1. กรณี Reply ข้อความ
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_id = target_user.id
        target_tag = f"@{target_user.username}" if target_user.username else f"ID: {target_id}"
    # 2. กรณีพิมพ์ต่อท้ายคำสั่ง
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

# คำสั่ง /unban (พิมพ์ /unban @username หรือ /unban ID)
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
        await update.message.reply_text("⚠️ ไม่พบผู้ใช้นี้ในระบบ กรุณาใช้คำสั่ง `/banlist` เพื่อดู ID", parse_mode="Markdown")
        return

    try:
        await context.bot.unban_chat_member(chat_id, target_id, only_if_banned=True)
        remove_ban(chat_id, target_id)
        await update.message.reply_text(f"✅ ปลดแบนผู้ใช้ {arg} (ID: `{target_id}`) เรียบร้อยแล้ว สามารถกดเข้ากลุ่มได้ตามปกติ", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ ไม่สามารถปลดแบนได้: {e}")

# คำสั่ง /banlist
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

# คำสั่ง /open on หรือ /open off (ระบบกันลิงก์)
async def open_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return

    chat_id = update.effective_chat.id
    if not context.args or context.args[0].lower() not in ["on", "off"]:
        await update.message.reply_text("⚠️ กรุณาระบุคำสั่ง `/open on` เพื่อเปิด หรือ `/open off` เพื่อปิดการกันลิงก์", parse_mode="Markdown")
        return

    mode = context.args[0].lower()
    if mode == "on":
        set_antilink(chat_id, 1)
        await update.message.reply_text("🛡️ **เปิดระบบป้องกันลิงก์แล้ว** (ข้อความที่มีลิงก์จะถูกลบทันที ยกเว้นแอดมิน)", parse_mode="Markdown")
    else:
        set_antilink(chat_id, 0)
        await update.message.reply_text("🔓 **ปิดระบบป้องกันลิงก์แล้ว**", parse_mode="Markdown")

# ================= 5. ตรวจจับข้อความและสมาชิกใหม่ =================
LINK_REGEX = re.compile(r'(https?://\S+|www\.\S+|t\.me/\S+)', re.IGNORECASE)

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.from_user:
        return

    user = update.message.from_user
    chat_id = update.effective_chat.id

    # บันทึก Username เข้าแคชไว้เสมอ
    if user.username:
        cache_user(user.username, user.id)

    # ตรวจสอบระบบกันลิงก์
    if get_antilink(chat_id):
        if not await is_admin(update, context):
            text = update.message.text or update.message.caption or ""
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

# ระบบต้อนรับสมาชิกใหม่ + ตรวจสอบแบน
async def greet_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            continue

        chat_id = update.effective_chat.id
        
        if member.username:
            cache_user(member.username, member.id)

        # ถ้าติดแบล็กลิสต์ ให้เตะ/แบนทันที
        if is_user_banned(chat_id, member.id):
            try:
                await context.bot.ban_chat_member(chat_id, member.id)
                continue
            except Exception:
                pass

        # ข้อความต้อนรับ
        user_mention = member.mention_html()
        welcome_text = f"♡ ยินดีต้อนรับเข้าสู่กลุ่มของเรา ♡\n{user_mention}"
        await update.message.reply_text(welcome_text, parse_mode="HTML")

# ================= 6. สตาร์ทบอท =================
def main():
    init_db()
    keep_alive()  # เปิด Port สำหรับ Render
    
    # 🔴 นำ Token ที่ได้จาก @BotFather มาใส่ตรงนี้
    BOT_TOKEN = "8510442078:AAEQxzafOyI-iuV9ZPhLWQBt3C7w7IlHy2g"

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("banlist", banlist_command))
    app.add_handler(CommandHandler("open", open_command))

    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, greet_new_member))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_messages))

    print("บอทเริ่มทำงานเรียบร้อย...")
    app.run_polling()

if __name__ == "__main__":
    main()
