from telegram import Update
from telegram.constants import MessageEntityType
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8510442078:AAFYfCBK6kT4mASprz_4836FecLq43l3P0E"

async def is_admin(chat, user_id):
    member = await chat.get_member(user_id)
    return member.status in ["administrator", "creator"]

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    sender = update.effective_user
    message = update.message

    if not await is_admin(chat, sender.id):
        await message.reply_text("คุณไม่ใช่แอดมิน ไม่มีสิทธิ์ใช้คำสั่งนี้")
        return

    target_user_id = None
    target_name = "สมาชิก"

    # แบนด้วยการแท็กชื่อ
    if message.entities:
        for entity in message.entities:
            if entity.type == MessageEntityType.TEXT_MENTION and entity.user:
                target_user_id = entity.user.id
                target_name = entity.user.first_name
                break

    # แบนด้วยการ Reply ข้อความ
    if not target_user_id and message.reply_to_message:
        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id
        target_name = target_user.first_name

    # แบนด้วย User ID (/ban 123456789)
    elif not target_user_id and context.args and context.args[0].isdigit():
        target_user_id = int(context.args[0])
        target_name = f"ID: {target_user_id}"

    if not target_user_id:
        await message.reply_text("วิธีใช้: Reply ข้อความคนที่จะแบน หรือพิมพ์ /ban @ชื่อ")
        return

    try:
        await chat.ban_member(target_user_id)
        await message.reply_text(f"แบน {target_name} เรียบร้อยแล้ว")
    except Exception as e:
        await message.reply_text(f"ไม่สามารถแบนได้: {e}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("ban", ban_user))
    app.run_polling()
