import os
import re
import logging
from datetime import datetime
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

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN not set")

# ---------------- HELP ----------------
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📒 ระบบบันทึกรายรับรายจ่าย\n\n"
        "วิธีใช้งาน:\n"
        "+500 เงินเข้า\n"
        "-100 ค่าอาหาร\n\n"
        "คำสั่ง:\n"
        "/balance - ดูยอดคงเหลือ\n"
        "/list - ดู 10 รายการล่าสุด\n"
        "/undo - ลบรายการล่าสุด\n"
        "/reset - ลบทั้งหมด\n"
    )
    await update.message.reply_text(msg)

# ---------------- HANDLE MESSAGE ----------------
async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    # รูปแบบ: +500 ค่าอาหาร
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
        await update.message.reply_text("❌ Database error")
        return

    cursor = conn.cursor()

    # ดึงยอดล่าสุด
    cursor.execute("""
        SELECT balance_after FROM history
        WHERE chat_id = %s
        ORDER BY id DESC LIMIT 1
    """, (chat_id,))
    last = cursor.fetchone()

    last_balance = last[0] if last else 0
    new_balance = last_balance + amount

    # บันทึก
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

# ---------------- LIST ----------------
async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

# ---------------- UNDO ----------------
async def undo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

# ---------------- RESET ----------------
async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

# ---------------- ERROR ----------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Exception: {context.error}")

# ---------------- MAIN ----------------
if __name__ == '__main__':
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler(["start", "help"], help_cmd))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("undo", undo_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

    app.add_error_handler(error_handler)

    logging.info("🚀 Expense Bot Running...")
    app.run_polling()
