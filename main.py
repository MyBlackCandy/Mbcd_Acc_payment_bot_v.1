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
            f"🆔 用户ID: {user_id}\n"
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
                f"🆔 用户ID: {user_id}\n" 
                f"👑 身份: Owner\n" 
                f"⏳ 剩余时间: {days} 天 {hours} 小时 {minutes} 分钟" 
            ) 
            return 
        else: 
            await update.message.reply_text(
                f"🆔 用户ID: {user_id}\n" 
                f"❌ 使用权限已过期,请联系管理员 @Mbcdcandy"
            ) 
            return 
        # ===== Assistant ===== 
    if assistant_row: 
        await update.message.reply_text(
            f"🆔 用户ID: {user_id}\n" 
            f"👥 身份: 此群操控者\n" 
            f"📌 仅限当前群组使用,请联系管理员 @Mbcdcandy"
        ) 
        return 
        # ===== 无权限 ===== 
    await update.message.reply_text(
        f"🆔 用户ID: {user_id}\n" 
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
        "📊 指令\n\n"

        
        "📈 /summary\n"
        "查看统计报表（总汇总 / 最近30天 / 最近12个月）\n\n"

        "↩️ /undo\n"
        "撤销最后一条记录\n\n"

        "🗑️ /reset\n"
        "清空当前群组所有记录（仅 Owner）\n\n"

        "🆔 /check\n"
        "查看当前账号身份与权限状态\n\n"

        "━━━━━━━━━━━━━━━━━━\n"
        "👑 仅限 Owner 使用\n"
        "拥有完整权限（需有使用期限）\n\n"

        "➕ 增加操作者用 /addassistant\n"
        "回复需要添加为助手，（必须用回复的方式）\n\n"

        "➖ 移除操作者用 /removeassistant\n"
        "回复需要移除助手，（必须用回复的方式）\n\n"

        "━━━━━━━━━━━━━━━━━━\n"
        
        "👑 仅限 MASTER 使用\n"
        "/adddays 用户ID 天数\n"
        "备注：（可用/chack 来查看用户ID）\n"
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


# ---------------- format_transaction_message ----------------

from collections import defaultdict

async def send_monthly_formatted_messages(update: Update, rows, current_balance, title="📒 **全部账目汇总**"):
    """
    按月份分段发送账目记录 (ภาษาจีน)
    """
    if not rows:
        await update.message.reply_text("📭 暂无账目记录")
        return

    # 1. 按月份分组数据: { '2024-01': [rows], '2024-02': [rows] }
    monthly_data = defaultdict(list)
    for r in rows:
        month_key = r[3].strftime('%Y-%m') 
        monthly_data[month_key].append(r)

    # 2. 发送主标题
    await update.message.reply_text(title, parse_mode='Markdown')

    # 3. 按月份循环发送 (从旧到新)
    sorted_months = sorted(monthly_data.keys())
    
    for month_key in sorted_months:
        month_rows = monthly_data[month_key]
        # 转换月份显示格式，例如 "2024年 03月"
        month_display = month_rows[0][3].strftime('%Y年 %m月')
        
        plus_sum = sum(r[1] for r in month_rows if r[1] > 0)
        minus_sum = sum(r[1] for r in month_rows if r[1] < 0)
        
        text_reply = f"📅 **月份: {month_display}**\n"
        text_reply += "------------------------------------------\n"

        for r in month_rows:
            dt_str = r[3].strftime('%m-%d %H:%M')
            amt_str = f"{'+' if r[1] > 0 else ''}{r[1]:,}"
            desc = r[0]
            bal_after = f"{r[2]:,}"
            
            # 格式: 日期 | 备注
            #       金额 | (余额)
            text_reply += f"🔹 {dt_str} | {desc} |💰 {amt_str} \n"
            text_reply += "------------------------------------------\n"

        # 月度小结
        text_reply += f"➕ 本月收款: {plus_sum:,}\n"
        text_reply += f"➖ 本月支付: {abs(minus_sum):,}\n"
        text_reply += f"💰 本月余额: {plus_sum + minus_sum:,}\n"
        
        # 发送该月份账单
        await update.message.reply_text(text_reply, parse_mode='Markdown')

    # 4. 发送最终总余额
    footer = f"━━━━━━━━━━━━━━━━━━\n💵 **当前总余额: {current_balance:,}**"
    await update.message.reply_text(footer, parse_mode='Markdown')

# ---------------- HANDLE MESSAGE ----------------
async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    role = await check_permission(update)
    if not role: return

    text = update.message.text.strip()
    match = re.match(r'^([+-])(\d+)\s*(.*)$', text)
    if not match: return

    sign, amount_str, description = match.groups()
    amount = int(amount_str)
    description = description if description else "未备注项目"
    if sign == '-': amount = -amount

    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name

    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()

    try:
        # 获取最后余额
        cursor.execute("SELECT balance_after FROM history WHERE chat_id = %s ORDER BY id DESC LIMIT 1", (chat_id,))
        last = cursor.fetchone()
        last_balance = last[0] if last else 0
        new_balance = last_balance + amount

        # 插入新记录
        cursor.execute("""
            INSERT INTO history (chat_id, amount, description, balance_after, user_name)
            VALUES (%s, %s, %s, %s, %s)
        """, (chat_id, amount, description, new_balance, user_name))
        conn.commit()

        # 获取所有历史记录按顺序排列
        cursor.execute("""
            SELECT description, amount, balance_after, timestamp
            FROM history WHERE chat_id = %s ORDER BY id ASC
        """, (chat_id,))
        rows = cursor.fetchall()

        # 调用月度格式化发送函数
        await send_monthly_formatted_messages(update, rows, new_balance, title="📋 **账目已更新并生成月度汇总**")

    finally:
        cursor.close()
        conn.close()


# ---------------- summary ----------------
async def summary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    role = await check_permission(update)
    if not role:
        return

    keyboard = [
        [InlineKeyboardButton("📊 全部统计", callback_data="summary_all")],
        [InlineKeyboardButton("📅 按月份查看", callback_data="summary_month_select")],
        [InlineKeyboardButton("📆 按年份查看", callback_data="summary_year_select")]
    ]

    await update.message.reply_text(
        "📊 请选择统计方式：",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------------- summary callback ----------------
async def summary_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    action = query.data

    conn = get_db_connection()
    cursor = conn.cursor()

    # ================= 全部统计 =================
    if action == "summary_all":

        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount END),0),
                COALESCE(SUM(CASE WHEN amount < 0 THEN amount END),0)
            FROM history
            WHERE chat_id = %s
        """, (chat_id,))
        income, expense = cursor.fetchone()
        expense_abs = abs(expense)
        net = income + expense

        # 按日
        cursor.execute("""
            SELECT DATE(timestamp),
                   COALESCE(SUM(CASE WHEN amount > 0 THEN amount END),0),
                   COALESCE(SUM(CASE WHEN amount < 0 THEN amount END),0)
            FROM history
            WHERE chat_id = %s
            GROUP BY DATE(timestamp)
            ORDER BY DATE(timestamp) DESC
        """, (chat_id,))
        daily = cursor.fetchall()

        # 按月
        cursor.execute("""
            SELECT TO_CHAR(timestamp,'YYYY-MM'),
                   COALESCE(SUM(CASE WHEN amount > 0 THEN amount END),0),
                   COALESCE(SUM(CASE WHEN amount < 0 THEN amount END),0)
            FROM history
            WHERE chat_id = %s
            GROUP BY TO_CHAR(timestamp,'YYYY-MM')
            ORDER BY 1 DESC
        """, (chat_id,))
        monthly = cursor.fetchall()

        # 按年
        cursor.execute("""
            SELECT TO_CHAR(timestamp,'YYYY'),
                   COALESCE(SUM(CASE WHEN amount > 0 THEN amount END),0),
                   COALESCE(SUM(CASE WHEN amount < 0 THEN amount END),0)
            FROM history
            WHERE chat_id = %s
            GROUP BY TO_CHAR(timestamp,'YYYY')
            ORDER BY 1 DESC
        """, (chat_id,))
        yearly = cursor.fetchall()

        text = "📊 全部统计\n━━━━━━━━━━━━━━━\n\n"
        text += f"收入: {income:,}\n"
        text += f"支出: {expense_abs:,}\n"
        text += f"净额: {net:,}\n\n"

        text += "📅 按日统计\n"
        for d, inc, exp in daily:
            text += f"{d} | 收入 {inc:,} | 支出 {abs(exp):,} | 净额 {(inc+exp):,}\n"

        text += "\n📆 按月统计\n"
        for m, inc, exp in monthly:
            text += f"{m} | 收入 {inc:,} | 支出 {abs(exp):,} | 净额 {(inc+exp):,}\n"

        text += "\n📈 按年统计\n"
        for y, inc, exp in yearly:
            text += f"{y} | 收入 {inc:,} | 支出 {abs(exp):,} | 净额 {(inc+exp):,}\n"

        await query.edit_message_text(text)

    # ================= 选择月份 =================
    elif action == "summary_month_select":

        cursor.execute("""
            SELECT DISTINCT TO_CHAR(timestamp,'YYYY-MM')
            FROM history
            WHERE chat_id = %s
            ORDER BY 1 DESC
            LIMIT 12
        """, (chat_id,))
        months = cursor.fetchall()

        keyboard = []
        for m in months:
            keyboard.append([
                InlineKeyboardButton(
                    m[0],
                    callback_data=f"summary_month:{m[0]}"
                )
            ])

        await query.edit_message_text(
            "📅 请选择月份：",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ================= 查看具体月份 =================
    elif action.startswith("summary_month:"):

        month = action.split(":")[1]

        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount END),0),
                COALESCE(SUM(CASE WHEN amount < 0 THEN amount END),0)
            FROM history
            WHERE chat_id=%s
            AND TO_CHAR(timestamp,'YYYY-MM')=%s
        """, (chat_id, month))
        income, expense = cursor.fetchone()
        expense_abs = abs(expense)
        net = income + expense

        cursor.execute("""
            SELECT DATE(timestamp),
                   COALESCE(SUM(CASE WHEN amount > 0 THEN amount END),0),
                   COALESCE(SUM(CASE WHEN amount < 0 THEN amount END),0)
            FROM history
            WHERE chat_id=%s
            AND TO_CHAR(timestamp,'YYYY-MM')=%s
            GROUP BY DATE(timestamp)
            ORDER BY DATE(timestamp)
        """, (chat_id, month))
        daily = cursor.fetchall()

        text = f"📅 {month} 月统计\n━━━━━━━━━━━━━━━\n\n"
        text += f"收入: {income:,}\n"
        text += f"支出: {expense_abs:,}\n"
        text += f"净额: {net:,}\n\n"

        for d, inc, exp in daily:
            text += f"{d} | 收入 {inc:,} | 支出 {abs(exp):,} | 净额 {(inc+exp):,}\n"

        await query.edit_message_text(text)

    # ================= 选择年份 =================
    elif action == "summary_year_select":

        cursor.execute("""
            SELECT DISTINCT TO_CHAR(timestamp,'YYYY')
            FROM history
            WHERE chat_id = %s
            ORDER BY 1 DESC
        """, (chat_id,))
        years = cursor.fetchall()

        keyboard = []
        for y in years:
            keyboard.append([
                InlineKeyboardButton(
                    y[0],
                    callback_data=f"summary_year:{y[0]}"
                )
            ])

        await query.edit_message_text(
            "📆 请选择年份：",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ================= 查看具体年份 =================
    elif action.startswith("summary_year:"):

        year = action.split(":")[1]

        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount END),0),
                COALESCE(SUM(CASE WHEN amount < 0 THEN amount END),0)
            FROM history
            WHERE chat_id=%s
            AND TO_CHAR(timestamp,'YYYY')=%s
        """, (chat_id, year))
        income, expense = cursor.fetchone()
        expense_abs = abs(expense)
        net = income + expense

        cursor.execute("""
            SELECT TO_CHAR(timestamp,'YYYY-MM'),
                   COALESCE(SUM(CASE WHEN amount > 0 THEN amount END),0),
                   COALESCE(SUM(CASE WHEN amount < 0 THEN amount END),0)
            FROM history
            WHERE chat_id=%s
            AND TO_CHAR(timestamp,'YYYY')=%s
            GROUP BY TO_CHAR(timestamp,'YYYY-MM')
            ORDER BY 1
        """, (chat_id, year))
        monthly = cursor.fetchall()

        text = f"📆 {year} 年统计\n━━━━━━━━━━━━━━━\n\n"
        text += f"收入: {income:,}\n"
        text += f"支出: {expense_abs:,}\n"
        text += f"净额: {net:,}\n\n"

        for m, inc, exp in monthly:
            text += f"{m} | 收入 {inc:,} | 支出 {abs(exp):,} | 净额 {(inc+exp):,}\n"

        await query.edit_message_text(text)

    cursor.close()
    conn.close()
# ---------------- undo ----------------
async def undo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    role = await check_permission(update)
    if not role: return

    chat_id = update.effective_chat.id
    conn = get_db_connection()
    if not conn: 
        await update.message.reply_text("❌ 数据库连接失败")
        return
        
    cursor = conn.cursor()

    try:
        # 查找最后一条记录
        cursor.execute("SELECT id FROM history WHERE chat_id = %s ORDER BY id DESC LIMIT 1", (chat_id,))
        last_row = cursor.fetchone()

        if not last_row:
            await update.message.reply_text("📭 暂无记录可撤销")
            return

        # 执行删除
        cursor.execute("DELETE FROM history WHERE id = %s", (last_row[0],))
        conn.commit()

        # 获取删除后的所有记录
        cursor.execute("""
            SELECT description, amount, balance_after, timestamp
            FROM history WHERE chat_id = %s ORDER BY id ASC
        """, (chat_id,))
        rows = cursor.fetchall()
        
        # 计算当前余额
        current_balance = rows[-1][2] if rows else 0

        # 调用月度格式化发送函数
        undo_title = "↩️ **已撤销最后一条记录，更新后的汇总如下：**"
        await send_monthly_formatted_messages(update, rows, current_balance, title=undo_title)

    finally:
        cursor.close()
        conn.close()



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
# ---------------- daily_report ----------------
async def daily_report(context: ContextTypes.DEFAULT_TYPE):

    chat_id = context.job.chat_id

    conn = get_db_connection()
    if not conn:
        return

    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            COALESCE(SUM(CASE WHEN amount > 0 THEN amount END),0),
            COALESCE(SUM(CASE WHEN amount < 0 THEN amount END),0)
        FROM history
        WHERE chat_id = %s
        AND DATE(timestamp) = CURRENT_DATE
    """, (chat_id,))

    income, expense = cursor.fetchone()
    cursor.close()
    conn.close()

    if income == 0 and expense == 0:
        text = "📅 今日统计\n━━━━━━━━━━━━━━━\n\n今天没有记录"
    else:
        net = income + expense
        text = (
            "📅 今日统计\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"收入: {income:,}\n"
            f"支出: {abs(expense):,}\n"
            f"净额: {net:,}"
        )

    await context.bot.send_message(chat_id=chat_id, text=text)

# ---------------- set_daily_report ----------------
async def set_daily_report(update: Update, context: ContextTypes.DEFAULT_TYPE):

    role = await check_permission(update)
    if not role:
        return

    if len(context.args) != 1:
        await update.message.reply_text("用法: /setreport HH:MM\n例如: /setreport 21:00")
        return

    try:
        hour, minute = map(int, context.args[0].split(":"))
    except:
        await update.message.reply_text("时间格式错误")
        return

    chat_id = update.effective_chat.id

    # ลบ job เดิมถ้ามี
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
    for job in current_jobs:
        job.schedule_removal()

    context.job_queue.run_daily(
        daily_report,
        time=datetime.strptime(context.args[0], "%H:%M").time(),
        chat_id=chat_id,
        name=str(chat_id)
    )

    await update.message.reply_text(
        f"✅ 每日自动报告已设置为 {context.args[0]}"
    )

# ---------------- stop_daily_report ----------------
async def stop_daily_report(update: Update, context: ContextTypes.DEFAULT_TYPE):

    role = await check_permission(update)
    if not role:
        return

    chat_id = update.effective_chat.id

    jobs = context.job_queue.get_jobs_by_name(str(chat_id))
    if not jobs:
        await update.message.reply_text("❌ 当前未设置自动报告")
        return

    for job in jobs:
        job.schedule_removal()

    await update.message.reply_text("✅ 已关闭每日自动报告")

# ---------------- MAIN ----------------
if __name__ == '__main__':
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    # ===== 基础命令 =====
    app.add_handler(CommandHandler(["start", "help"], help_cmd))
    app.add_handler(CommandHandler("check", check_status))
    
    app.add_handler(CommandHandler("summary", summary_cmd))
    app.add_handler(CommandHandler("undo", undo_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CommandHandler("setreport", set_daily_report))
    app.add_handler(CommandHandler("stopreport", stop_daily_report))

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
    app.add_handler(
        CallbackQueryHandler(
            summary_callback, 
            pattern="^summary_"
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
