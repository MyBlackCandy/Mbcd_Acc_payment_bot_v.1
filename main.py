import os
import re
import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from database import init_db, get_db_connection

# ---------------- CONFIG ----------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
MASTER_ADMIN = os.getenv("ADMIN_ID")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN not set")

# ---------------- PERMISSION SYSTEM ----------------
async def check_permission(update: Update):
    user_id = update.effective_user.id

    # MASTER ใช้งานได้ตลอด
    if str(user_id) == str(MASTER_ADMIN):
        return True

    conn = get_db_connection()
    if not conn:
        return False

    cursor = conn.cursor()
    cursor.execute("SELECT expire_date FROM users WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if row and row[0] and row[0] > datetime.utcnow():
        return True

    await update.message.reply_text("❌ สิทธิ์หมดอายุ กรุณาติดต่อแอดมิน")
    return False


# ---------------- CHECK STATUS ----------------
async def check_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if str(user_id) == str(MASTER_ADMIN):
        await update.message.reply_text(
            f"🆔 ID: {user_id}\n👑 สถานะ: MASTER (ไม่จำกัดเวลา)"
        )
        return

    conn = get_db_connection()
    if not conn:
        return

    cursor = conn.cursor()
    cursor.execute("SELECT expire_date FROM users WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if row and row[0]:
        remaining = row[0] - datetime.utcnow()
        if remaining.total_seconds() > 0:
            await update.message.reply_text(
                f"🆔 ID: {user_id}\n"
                f"⏳ เหลือเวลา: {remaining.days} วัน "
                f"{remaining.seconds//3600} ชั่วโมง"
            )
        else:
            await update.message.reply_text("❌ สิทธิ์หมดอายุแล้ว")
    else:
        await update.message.reply_text("❌ ยังไม่ได้เปิดใช้งาน")


# ---------------- ADD DAYS (MASTER ONLY) ----------------
async def add_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(MASTER_ADMIN):
        return

    if len(context.args) != 2:
        await update.message.reply_text("ใช้: /adddays USER_ID จำนวนวัน")
        return

    try:
        target_id = int(context.args[0])
        days = int(context.args[1])
    except:
        await update.message.reply_text("รูปแบบไม่ถูกต้อง")
        return

    conn = get_db_connection()
    if not conn:
        return

    cursor = conn.cursor()
    cursor.execute("SELECT expire_date FROM users WHERE user_id = %s", (target_id,))
    row = cursor.fetchone()

    if row and row[0] and row[0] > datetime.utcnow():
        new_expire = row[0] + timedelta(days=days)
    else:
        new_expire = datetime.utcnow() + timedelta(days=days)

    cursor.execute("""
        INSERT INTO users (user_id, expire_date)
        VALUES (%s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET expire_date = %s
    """, (target_id, new_expire, new_expire))

    conn.commit()
    cursor.close()
    conn.close()

    await update.message.reply_text(
        f"✅ เพิ่ม {days} วัน ให้ {target_id}\nหมดอายุ: {new_expire}"
    )


# ---------------- HELP ----------------
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📒 *收支记账机器人*\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        "💡 *如何登记账目*\n"
        "请按以下格式输入：\n\n"
        "  ➕ `+500 充值`\n"
        "  ➖ `-100 吃饭`\n\n"
        "系统会自动计算余额\n\n"

        "━━━━━━━━━━━━━━━━━━\n"
        "📊 *常用指令*\n\n"

        "💰 `/balance`\n"
        "查看当前余额\n\n"

        "📄 `/list`\n"
        "查看最近 10 条记录\n\n"

        "↩️ `/undo`\n"
        "撤销最后一条记录\n\n"

        "🗑️ `/reset`\n"
        "清空当前群组所有记录\n\n"

        "━━━━━━━━━━━━━━━━━━\n"
        "🔐 *使用权限系统*\n\n"

        "🆔 `/check`\n"
        "查看当前账号权限状态\n\n"

        "👑 *仅限 MASTER 使用*\n"
        "`/adddays 用户ID 天数`\n"
        "例如：\n"
        "`/adddays 123456789 30`\n"
        "给该用户增加 30 天使用期限\n\n"

        "━━━━━━━━━━━━━━━━━━\n"
        "📌 *说明*\n"
        "• 系统按群组独立记账\n"
        "• 每个群组数据互不影响\n"
        "• 权限到期后将无法继续使用\n\n"

        "🚀 如需开通权限，请联系管理员"
    )

    await update.message.reply_text(msg, parse_mode="Markdown")



# ---------------- HANDLE MESSAGE ----------------
async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    if not await check_permission(update):
        return

    text = update.message.text.strip()
    match = re.match(r'^([+-])(\d+)\s*(.*)$', text)
    if not match:
        return

    sign = match.group(1)
    amount = int(match.group(2))
    description = match.group(3) if match.group(3) else "ไม่ระบุรายการ"

    if sign == '-':
        amount = -amount

    chat_id = update.effective_chat.id

    conn = get_db_connection()
    if not conn:
        return

    cursor = conn.cursor()

    cursor.execute("""
        SELECT balance_after FROM history
        WHERE chat_id = %s
        ORDER BY id DESC LIMIT 1
    """, (chat_id,))
    last = cursor.fetchone()

    last_balance = last[0] if last else 0
    new_balance = last_balance + amount

    cursor.execute("""
        INSERT INTO history (chat_id, amount, description, balance_after, user_name)
        VALUES (%s, %s, %s, %s, %s)
    """, (chat_id, amount, description, new_balance, update.message.from_user.first_name))

    conn.commit()
    cursor.close()
    conn.close()

    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    await update.message.reply_text(
        f"📅 {now}\n"
        f"📌 {description}\n"
        f"{'💵 +' if amount > 0 else '💸 '}{amount}\n"
        f"💰 คงเหลือ: {new_balance}"
    )


# ---------------- BALANCE ----------------
async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update):
        return

    chat_id = update.effective_chat.id

    conn = get_db_connection()
    if not conn:
        return

    cursor = conn.cursor()
    cursor.execute("""
        SELECT balance_after FROM history
        WHERE chat_id = %s
        ORDER BY id DESC LIMIT 1
    """, (chat_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    balance = row[0] if row else 0

    await update.message.reply_text(f"💰 ยอดคงเหลือปัจจุบัน: {balance}")

# ---------------- list ----------------
async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update):
        return

    chat_id = update.effective_chat.id
    conn = get_db_connection()
    if not conn:
        return

    cursor = conn.cursor()
    cursor.execute("""
        SELECT description, amount, balance_after, timestamp
        FROM history
        WHERE chat_id = %s
        ORDER BY id DESC LIMIT 10
    """, (chat_id,))

    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        await update.message.reply_text("ยังไม่มีรายการ")
        return

    text = "📄 10 รายการล่าสุด\n\n"

    for r in rows:
        text += (
            f"{r[3].strftime('%m-%d %H:%M')} | "
            f"{r[1]} | "
            f"คงเหลือ {r[2]}\n"
            f"📌 {r[0]}\n\n"
        )

    await update.message.reply_text(text)

# ---------------- undo ----------------
async def undo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update):
        return

    chat_id = update.effective_chat.id
    conn = get_db_connection()
    if not conn:
        return

    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM history
        WHERE id = (
            SELECT id FROM history
            WHERE chat_id = %s
            ORDER BY id DESC LIMIT 1
        )
    """, (chat_id,))

    conn.commit()
    cursor.close()
    conn.close()

    await update.message.reply_text("↩️ ลบรายการล่าสุดแล้ว")

# ---------------- reset ----------------
async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update):
        return

    chat_id = update.effective_chat.id
    conn = get_db_connection()
    if not conn:
        return

    cursor = conn.cursor()
    cursor.execute("DELETE FROM history WHERE chat_id = %s", (chat_id,))
    conn.commit()
    cursor.close()
    conn.close()

    await update.message.reply_text("🗑️ ลบข้อมูลทั้งหมดแล้ว")

# ---------------- MAIN ----------------
if __name__ == '__main__':
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler(["start", "help"], help_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("undo", undo_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CommandHandler("check", check_status))
    app.add_handler(CommandHandler("adddays", add_days))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

    logging.info("🚀 Expense Bot Running...")
    app.run_polling()
