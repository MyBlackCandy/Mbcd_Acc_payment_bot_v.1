import os
import re
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
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

# ================= OWNER =================
async def is_owner(chat_id, user_id):

    if str(user_id) == str(MASTER_ADMIN):
        return True

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT expire_date FROM users WHERE user_id=%s",
        (user_id,)
    )
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    return True if row and row[0] and row[0] > datetime.utcnow() else False


# ================= ASSISTANT =================
async def is_assistant(chat_id, user_id):

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM assistants WHERE chat_id=%s AND assistant_id=%s",
        (chat_id, user_id)
    )
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    return True if row else False


# ================= ROLE CHECK =================
async def check_permission(update: Update):

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if await is_owner(chat_id, user_id):
        return "owner"

    if await is_assistant(chat_id, user_id):
        return "assistant"

    await update.message.reply_text("❌ 无使用权限")
    return None


# ================= ADD ASSISTANT =================
async def add_assistant(update: Update, context: ContextTypes.DEFAULT_TYPE):

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_owner(chat_id, user_id):
        await update.message.reply_text("❌ 仅 Owner 可添加助手")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("请回复要添加为助手的人")
        return

    assistant_id = update.message.reply_to_message.from_user.id

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO assistants (chat_id, owner_id, assistant_id)
        VALUES (%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, (chat_id, user_id, assistant_id))
    conn.commit()
    cursor.close()
    conn.close()

    await update.message.reply_text("✅ 助手添加成功")


# ================= REMOVE ASSISTANT =================
async def remove_assistant(update: Update, context: ContextTypes.DEFAULT_TYPE):

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_owner(chat_id, user_id):
        await update.message.reply_text("❌ 仅 Owner 可移除助手")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("请回复要移除的助手")
        return

    assistant_id = update.message.reply_to_message.from_user.id

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM assistants
        WHERE chat_id=%s AND assistant_id=%s
    """, (chat_id, assistant_id))
    conn.commit()
    cursor.close()
    conn.close()

    await update.message.reply_text("✅ 助手已移除")
# ---------------- CHECK STATUS ----------------
async def check_status(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # ===== MASTER =====
    if str(user_id) == str(MASTER_ADMIN):
        await update.message.reply_text(
            f"🆔 用户ID: `{user_id}`\n"
            f"👑 身份: MASTER\n"
            f"⏳ 状态: 永久有效"
        )
        return

    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ 数据库连接错误")
        return

    cursor = conn.cursor()

    # 查使用期限
    cursor.execute(
        "SELECT expire_date FROM users WHERE user_id = %s",
        (user_id,)
    )
    user_row = cursor.fetchone()

    # 查 Assistant
    cursor.execute(
        "SELECT 1 FROM assistants WHERE chat_id=%s AND assistant_id=%s",
        (chat_id, user_id)
    )
    assistant_row = cursor.fetchone()

    cursor.close()
    conn.close()

    # ===== Owner =====
    if user_row and user_row[0]:
        remaining = user_row[0] - datetime.utcnow()

        if remaining.total_seconds() > 0:
            days = remaining.days
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60

            await update.message.reply_text(
                f"🆔 用户ID: `{user_id}`\n"
                f"👑 身份: 授权者\n"
                f"⏳ 剩余时间: {days} 天 {hours} 小时 {minutes} 分钟"
            )
            return
        else:
            await update.message.reply_text(
                f"🆔 用户ID: `{user_id}`\n"
                f"❌ 使用权限已过期,请联系管理员 @Mbcdcandy"
            )
            return

    # ===== Assistant =====
    if assistant_row:
        await update.message.reply_text(
            f"🆔 用户ID: `{user_id}`\n"
            f"👥 身份:  群操控者\n"
            f"📌 仅限当前群组使用,请联系管理员 @Mbcdcandy"
        )
        return

    # ===== 无权限 =====
    await update.message.reply_text(
        f"🆔 用户ID: `{user_id}`\n"
        f"❌ 当前群组无使用权限,请联系管理员 @Mbcdcandy"
    )

# ---------------- ADD DAYS (MASTER ONLY) ----------------
async def add_days(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    # ===== MASTER ONLY =====
    if str(user_id) != str(MASTER_ADMIN):
        await update.message.reply_text("❌ 仅 MASTER 可使用此命令")
        return

    if len(context.args) != 2:
        await update.message.reply_text("用法: /adddays USER_ID 天数\n例如: /adddays 123456 30")
        return

    try:
        target_id = int(context.args[0])
        days = int(context.args[1])   # 支持负数
    except:
        await update.message.reply_text("❌ 参数格式错误")
        return

    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ 数据库连接失败")
        return

    cursor = conn.cursor()

    cursor.execute(
        "SELECT expire_date FROM users WHERE user_id=%s",
        (target_id,)
    )
    row = cursor.fetchone()

    now = datetime.utcnow()

    # ===== 计算新时间 =====
    if row and row[0] and row[0] > now:
        base_time = row[0]
    else:
        base_time = now

    new_expire = base_time + timedelta(days=days)

    # 防止时间小于当前时间太多
    if new_expire < now:
        new_expire = now

    cursor.execute("""
        INSERT INTO users (user_id, expire_date)
        VALUES (%s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET expire_date=%s
    """, (target_id, new_expire, new_expire))

    conn.commit()
    cursor.close()
    conn.close()

    # ===== 剩余时间计算 =====
    remaining = new_expire - now
    days_left = remaining.days

    await update.message.reply_text(
        f"✅ 已调整 {days} 天\n\n"
        f"👤 用户: {target_id}\n"
        f"📅 新到期时间: {new_expire.strftime('%Y-%m-%d %H:%M')}\n"
        f"⏳ 剩余天数: {days_left} 天"
    )

# ---------------- HELP ----------------
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    msg = (
        "📒 团队收支记账机器人\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        "💡 记账方式\n"
        "请输入以下格式：\n\n"
        "➕ +500 充值\n"
        "➖ -100 吃饭\n\n"
        "系统会自动计算余额\n\n"

        "━━━━━━━━━━━━━━━━━━\n"
        "📊 账务指令\n\n"

        "💰 /balance\n"
        "查看最近 100 条记录\n\n"

        "📈 /summary\n"
        "查看统计报表（总汇总 / 最近30天 / 最近12个月）\n\n"

        "↩️ /undo\n"
        "撤销最后一条记录\n\n"

        "🗑️ /reset\n"
        "清空当前群组所有记录（仅 Owner）\n\n"

        "━━━━━━━━━━━━━━━━━━\n"
        "👥 团队权限\n\n"

        "👑 Owner\n"
        "拥有完整权限（需有使用期限）\n\n"

        "👥 Assistant\n"
        "仅限当前群组使用\n"
        "可记账 /undo /balance /summary\n\n"

        "➕ /addassistant\n"
        "回复某人添加为助手（仅 Owner）\n\n"

        "➖ /removeassistant\n"
        "回复某人移除助手（仅 Owner）\n\n"

        "━━━━━━━━━━━━━━━━━━\n"
        "🔐 权限管理\n\n"

        "🆔 /check\n"
        "查看当前账号身份与权限状态\n\n"

        "👑 仅限 MASTER 使用\n"
        "/adddays 用户ID 天数\n"
        "例如：\n"
        "/adddays 123456789 30\n"
        "增加 30 天使用期限\n\n"

        "━━━━━━━━━━━━━━━━━━\n"
        "📌 系统说明\n"
        "• 数据按群组独立存储\n"
        "• 不同群组数据互不影响\n"
        "• 权限过期将无法继续使用\n\n"

        "🚀 如需开通或续费权限，请联系管理员 @Mbcdcandy"
    )

    await update.message.reply_text(msg)
    
# ---------------- HANDLE MESSAGE ----------------
async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message or not update.message.text:
        return

    role = await check_permission(update)
    if not role:   # ไม่มีสิทธิ์
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
    user_name = update.effective_user.first_name

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

    # 插入记录
    cursor.execute("""
        INSERT INTO history (chat_id, amount, description, balance_after, user_name)
        VALUES (%s, %s, %s, %s, %s)
    """, (chat_id, amount, description, new_balance, user_name))

    conn.commit()

    # 取最近 6 条
    cursor.execute("""
        SELECT description, amount, balance_after, timestamp
        FROM history
        WHERE chat_id = %s
        ORDER BY id DESC LIMIT 6
    """, (chat_id,))

    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    rows.reverse()
    display_rows = rows[-5:] if len(rows) > 5 else rows

    text_reply = "📋 最近记录:\n\n"

    if len(rows) > 5:
        text_reply += "...\n"

    for r in display_rows:
        text_reply += (
            f"{r[3].strftime('%m-%d %H:%M')} | "
            f"{'+' if r[1] > 0 else ''}{r[1]:,} | "
            f"余额 {r[2]:,} | "
            f"{r[0]}\n"
        )

    text_reply += "\n━━━━━━━━━━━━━━━\n"
    text_reply += f"💰 当前余额: {new_balance:,}"

    await update.message.reply_text(text_reply)

# ---------------- BALANCE ----------------
async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    role = await check_permission(update)
    if not role:
        return

    chat_id = update.effective_chat.id

    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ 数据库连接失败")
        return

    cursor = conn.cursor()

    # จำกัด 100 รายการล่าสุด ป้องกันยาวเกิน
    cursor.execute("""
        SELECT description, amount, balance_after, timestamp
        FROM history
        WHERE chat_id = %s
        ORDER BY id DESC
        LIMIT 100
    """, (chat_id,))

    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        await update.message.reply_text("📭 暂无记录")
        return

    rows.reverse()

    header = "📒 最近 100 条账目记录\n\n"
    footer = f"\n━━━━━━━━━━━━━━━\n💰 当前余额: {rows[-1][2]:,}"

    message = header

    for r in rows:
        line = (
            f"{r[3].strftime('%m-%d %H:%M')} | "
            f"{'+' if r[1] > 0 else ''}{r[1]:,} | "
            f"余额 {r[2]:,} | "
            f"{r[0]}\n"
        )

        # ถ้าใกล้ 4096 ตัวอักษร ให้ส่งก่อน
        if len(message + line + footer) > 3900:
            await update.message.reply_text(message)
            message = ""

        message += line

    message += footer

    await update.message.reply_text(message)


# ---------------- summary ----------------
async def summary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    role = await check_permission(update)
    if not role:
        return

    chat_id = update.effective_chat.id
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ 数据库连接失败")
        return

    cursor = conn.cursor()

    # ================= 总体统计 =================
    cursor.execute("""
        SELECT 
            COALESCE(SUM(CASE WHEN amount > 0 THEN amount END),0),
            COALESCE(SUM(CASE WHEN amount < 0 THEN amount END),0)
        FROM history
        WHERE chat_id = %s
    """, (chat_id,))
    total_income, total_expense = cursor.fetchone()
    total_net = total_income + total_expense

    # ================= 日统计 (最近30天) =================
    cursor.execute("""
        SELECT 
            DATE(timestamp),
            COALESCE(SUM(CASE WHEN amount > 0 THEN amount END),0),
            COALESCE(SUM(CASE WHEN amount < 0 THEN amount END),0)
        FROM history
        WHERE chat_id = %s
        GROUP BY DATE(timestamp)
        ORDER BY DATE(timestamp) DESC
        LIMIT 30
    """, (chat_id,))
    daily_rows = cursor.fetchall()

    # ================= 月统计 (最近12个月) =================
    cursor.execute("""
        SELECT 
            TO_CHAR(timestamp, 'YYYY-MM'),
            COALESCE(SUM(CASE WHEN amount > 0 THEN amount END),0),
            COALESCE(SUM(CASE WHEN amount < 0 THEN amount END),0)
        FROM history
        WHERE chat_id = %s
        GROUP BY TO_CHAR(timestamp, 'YYYY-MM')
        ORDER BY TO_CHAR(timestamp, 'YYYY-MM') DESC
        LIMIT 12
    """, (chat_id,))
    monthly_rows = cursor.fetchall()

    cursor.close()
    conn.close()

    if not daily_rows:
        await update.message.reply_text("📭 暂无账务记录")
        return

    text = "📊 财务统计中心\n"
    text += "━━━━━━━━━━━━━━━\n\n"

    # ===== 总体 =====
    text += "📌 总体汇总\n"
    text += f"总收入: {total_income:,}\n"
    text += f"总支出: {total_expense:,}\n"
    text += f"总净额: {total_net:,}\n\n"

    # ===== 每日 =====
    text += "📅 最近 30 天\n"
    for day, income, expense in daily_rows:
        net = income + expense
        text += f"{day} | 收入 {income:,} | 支出 {expense:,} | 净额 {net:,}\n"

    text += "\n📆 最近 12 个月\n"
    for month, income, expense in monthly_rows:
        net = income + expense
        text += f"{month} | 收入 {income:,} | 支出 {expense:,} | 净额 {net:,}\n"

    # ป้องกันเกิน Telegram limit
    if len(text) > 3900:
        parts = [text[i:i+3900] for i in range(0, len(text), 3900)]
        for part in parts:
            await update.message.reply_text(part)
    else:
        await update.message.reply_text(text)
    
# ---------------- list ----------------


# ---------------- undo ----------------
async def undo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    role = await check_permission(update)
    if not role:
        return

    chat_id = update.effective_chat.id

    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ 数据库连接失败")
        return

    cursor = conn.cursor()

    # ดึงแถวล่าสุด
    cursor.execute("""
        SELECT id, amount
        FROM history
        WHERE chat_id = %s
        ORDER BY id DESC
        LIMIT 1
    """, (chat_id,))

    last_row = cursor.fetchone()

    if not last_row:
        cursor.close()
        conn.close()
        await update.message.reply_text("📭 暂无记录可撤销")
        return

    last_id, last_amount = last_row

    # ลบรายการล่าสุด
    cursor.execute("""
        DELETE FROM history
        WHERE id = %s
    """, (last_id,))

    conn.commit()

    # ดึงยอดล่าสุดใหม่
    cursor.execute("""
        SELECT balance_after
        FROM history
        WHERE chat_id = %s
        ORDER BY id DESC
        LIMIT 1
    """, (chat_id,))

    balance_row = cursor.fetchone()

    current_balance = balance_row[0] if balance_row else 0

    # ดึง 5 รายการล่าสุดมาแสดง
    cursor.execute("""
        SELECT description, amount, balance_after, timestamp
        FROM history
        WHERE chat_id = %s
        ORDER BY id DESC
        LIMIT 5
    """, (chat_id,))

    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    rows.reverse()

    text_reply = "↩️ 已撤销最后一条记录\n"
    text_reply += "━━━━━━━━━━━━━━━\n\n"

    if not rows:
        text_reply += "📭 当前暂无记录\n"
        text_reply += "\n💰 当前余额: 0"
        await update.message.reply_text(text_reply)
        return

    text_reply += "📋 当前记录\n\n"

    for r in rows:
        text_reply += (
            f"{r[3].strftime('%m-%d %H:%M')} | "
            f"{'+' if r[1] > 0 else ''}{r[1]:,} | "
            f"余额 {r[2]:,} | "
            f"{r[0]}\n"
        )

    text_reply += "\n━━━━━━━━━━━━━━━\n"
    text_reply += f"💰 当前余额: {current_balance:,}"

    await update.message.reply_text(text_reply)


# ---------------- reset ----------------
# ---------------- reset ----------------
async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    role = await check_permission(update)
    if not role:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_owner(chat_id, user_id):
        await update.message.reply_text("❌ 仅 Owner 可以清空记录")
        return

    keyboard = [[
        InlineKeyboardButton(
            "✅ 确认清空",
            callback_data=f"confirm_reset:{chat_id}"
        ),
        InlineKeyboardButton(
            "❌ 取消",
            callback_data=f"cancel_reset:{chat_id}"
        )
    ]]

    await update.message.reply_text(
        "⚠️ 确认清空所有记录？\n此操作不可恢复！",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------------- reset callback ----------------
async def reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    if not query.data or ":" not in query.data:
        return

    action, data_chat_id = query.data.split(":")
    chat_id = query.message.chat.id
    user_id = query.from_user.id

    # ป้องกันข้ามกลุ่ม
    if str(chat_id) != str(data_chat_id):
        await query.edit_message_text("❌ 操作无效")
        return

    if not await is_owner(chat_id, user_id):
        await query.edit_message_text("❌ 无权限执行")
        return

    if action == "cancel_reset":
        await query.edit_message_text("✅ 已取消")
        return

    if action == "confirm_reset":
        conn = get_db_connection()
        if not conn:
            await query.edit_message_text("❌ 数据库连接失败")
            return

        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM history WHERE chat_id = %s",
                (chat_id,)
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            await query.edit_message_text("❌ 清空失败，请稍后重试")
            cursor.close()
            conn.close()
            return

        cursor.close()
        conn.close()

        await query.edit_message_text(
            "🗑️ 已清空所有记录\n\n💰 当前余额: 0"
        )

# ---------------- MAIN ----------------
# ---------------- GLOBAL ERROR HANDLER ----------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error(
        msg="Exception while handling update:",
        exc_info=context.error
    )

    try:
        if update and hasattr(update, "effective_message"):
            await update.effective_message.reply_text(
                "❌ 系统发生错误，请稍后再试"
            )
    except:
        pass


# ---------------- MAIN ----------------
if __name__ == '__main__':
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    # ===== 基础命令 =====
    app.add_handler(CommandHandler(["start", "help"], help_cmd))
    app.add_handler(CommandHandler("check", check_status))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("summary", summary_cmd))
    app.add_handler(CommandHandler("undo", undo_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))

    # ===== Owner 管理命令 =====
    app.add_handler(CommandHandler("adddays", add_days))
    app.add_handler(CommandHandler("addassistant", add_assistant))
    app.add_handler(CommandHandler("removeassistant", remove_assistant))

    # ===== Callback (按钮) =====
    app.add_handler(
        CallbackQueryHandler(
            reset_callback,
            pattern="^(confirm_reset|cancel_reset)"
        )
    )

    # ===== 普通文本记账 =====
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_msg
        )
    )

    # ===== 全局错误处理 =====
    app.add_error_handler(error_handler)

    logging.info("🚀 Expense Bot Running...")
    app.run_polling(
        drop_pending_updates=True
    )
