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

    # MASTER 永久有效
    if str(user_id) == str(MASTER_ADMIN):
        return True

    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ 数据库连接失败")
        return False

    cursor = conn.cursor()
    cursor.execute("SELECT expire_date FROM users WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if row and row[0] and row[0] > datetime.utcnow():
        return True

    await update.message.reply_text(
        "❌ 使用权限已过期\n"
        "请联系管理员 `@Mbcdcandy` 开通权限"
    )
    return False

# ---------------- CHECK STATUS ----------------
async def check_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # MASTER 永久权限
    if str(user_id) == str(MASTER_ADMIN):
        await update.message.reply_text(
            f"🆔 用户ID:`{user_id}`\n"
            f"👑 权限状态: MASTER（永久有效）"
        )
        return

    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ 数据库连接错误")
        return

    cursor = conn.cursor()
    cursor.execute("SELECT expire_date FROM users WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if row and row[0]:
        remaining = row[0] - datetime.utcnow()

        if remaining.total_seconds() > 0:
            days = remaining.days
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60

            await update.message.reply_text(
                f"🆔 用户ID: `{user_id}`\n"
                f"⏳ 剩余时间: {days} 天 {hours} 小时 {minutes} 分钟"
            )
        else:
            await update.message.reply_text(
                f"🆔 用户ID: `{user_id}`\n"
                f"❌ 权限已过期"
            )
    else:
        await update.message.reply_text(
            f"🆔 用户ID: `{user_id}`\n"
            f"⚠️ 尚未开通使用权限"
        )

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
        f"✅ 增加 {days} 天 给 {target_id}\n使用到期: {new_expire}"
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
        "查看全部记录\n\n"

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
    description = match.group(3) if match.group(3) else "未备注"

    if sign == '-':
        amount = -amount

    chat_id = update.effective_chat.id

    conn = get_db_connection()
    if not conn:
        return

    cursor = conn.cursor()

    # 取最后余额
    cursor.execute("""
        SELECT balance_after FROM history
        WHERE chat_id = %s
        ORDER BY id DESC LIMIT 1
    """, (chat_id,))
    last = cursor.fetchone()

    last_balance = last[0] if last else 0
    new_balance = last_balance + amount

    # 插入新记录
    cursor.execute("""
        INSERT INTO history (chat_id, amount, description, balance_after, user_name)
        VALUES (%s, %s, %s, %s, %s)
    """, (chat_id, amount, description, new_balance, update.message.from_user.first_name))

    conn.commit()

    # 取最近记录（最多6条）
    cursor.execute("""
        SELECT description, amount, balance_after, timestamp
        FROM history
        WHERE chat_id = %s
        ORDER BY id DESC LIMIT 6
    """, (chat_id,))

    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    rows.reverse()  # 时间顺序

    display_rows = rows[-5:] if len(rows) > 5 else rows

    text_reply = "📋 最近记录:\n\n"

    if len(rows) > 5:
        text_reply += "...\n"

    for r in display_rows:
        text_reply += (
            f"{r[3].strftime('%m-%d %H:%M')} | "
            f"{'+' if r[1]>0 else ''}{r[1]} | "
            f"余额 {r[2]}\n"
            f"📌 {r[0]}\n\n"
        )

    text_reply += "━━━━━━━━━━━━━━━\n"
    text_reply += f"💰 当前余额: {new_balance}"

    await update.message.reply_text(text_reply)

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
        SELECT description, amount, balance_after, timestamp
        FROM history
        WHERE chat_id = %s
        ORDER BY id ASC
    """, (chat_id,))

    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        await update.message.reply_text("📭 暂无记录")
        return

    text = "📒 全部账目记录\n\n"

    for r in rows:
        text += (
            f"{r[3].strftime('%m-%d %H:%M')} | "
            f"{'+' if r[1]>0 else ''}{r[1]} | "
            f"余额 {r[2]}\n"
            f"📌 {r[0]}\n\n"
        )

    text += "━━━━━━━━━━━━━━━\n"
    text += f"💰 当前余额: {rows[-1][2]}"

    await update.message.reply_text(text)


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
        await update.message.reply_text("没有记录")
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

    # ลบรายการล่าสุด
    cursor.execute("""
        DELETE FROM history
        WHERE id = (
            SELECT id FROM history
            WHERE chat_id = %s
            ORDER BY id DESC LIMIT 1
        )
    """, (chat_id,))
    conn.commit()

    # ดึงรายการล่าสุดหลังลบ (สูงสุด 6 รายการ)
    cursor.execute("""
        SELECT description, amount, balance_after, timestamp
        FROM history
        WHERE chat_id = %s
        ORDER BY id DESC LIMIT 6
    """, (chat_id,))

    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        await update.message.reply_text("🗑️ 已撤销，当前暂无记录")
        return

    rows.reverse()  # เรียงตามเวลาเก่า → ใหม่

    display_rows = rows[-5:] if len(rows) > 5 else rows

    text_reply = "↩️ 已撤销最后一条记录\n\n"
    text_reply += "📋 当前记录:\n\n"

    if len(rows) > 5:
        text_reply += "...\n"

    for r in display_rows:
        text_reply += (
            f"{r[3].strftime('%m-%d %H:%M')} | "
            f"{'+' if r[1] > 0 else ''}{r[1]} | "
            f"余额 {r[2]}\n"
            f"📌 {r[0]}\n\n"
        )

    text_reply += "━━━━━━━━━━━━━━━\n"
    text_reply += f"💰 当前余额: {rows[-1][2]}"

    await update.message.reply_text(text_reply)


# ---------------- reset ----------------
async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update):
        return

    chat_id = update.effective_chat.id
    conn = get_db_connection()
    if not conn:
        return

    cursor = conn.cursor()

    # ลบข้อมูลทั้งหมดของกลุ่ม
    cursor.execute("DELETE FROM history WHERE chat_id = %s", (chat_id,))
    conn.commit()

    # ตรวจสอบว่ามีข้อมูลเหลือไหม
    cursor.execute("""
        SELECT description, amount, balance_after, timestamp
        FROM history
        WHERE chat_id = %s
        ORDER BY id DESC LIMIT 6
    """, (chat_id,))

    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        await update.message.reply_text(
            "🗑️ 已清空所有记录\n\n"
            "📭 当前暂无任何账目记录\n"
            "💰 当前余额: 0"
        )
        return

    # เผื่อในอนาคตมีเงื่อนไขพิเศษ
    rows.reverse()
    display_rows = rows[-5:] if len(rows) > 5 else rows

    text_reply = "🗑️ 已清空记录\n\n"
    text_reply += "📋 当前记录:\n\n"

    if len(rows) > 5:
        text_reply += "...\n"

    for r in display_rows:
        text_reply += (
            f"{r[3].strftime('%m-%d %H:%M')} | "
            f"{'+' if r[1] > 0 else ''}{r[1]} | "
            f"余额 {r[2]}\n"
            f"📌 {r[0]}\n\n"
        )

    text_reply += "━━━━━━━━━━━━━━━\n"
    text_reply += f"💰 当前余额: {rows[-1][2]}"

    await update.message.reply_text(text_reply)


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
