import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import db

logging.basicConfig(level=logging.INFO)

ADMIN_TOKEN = os.environ.get("ADMIN_BOT_TOKEN")
ADMIN_IDS = {int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()}


def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("دسترسی نداری.")
            return
        return await func(update, context)

    return wrapper


@admin_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "پنل ادمین 🛠\n\n"
        "/stats — آمار کلی\n"
        "/users [صفحه] — لیست کاربرها\n"
        "/search <آیدی یا یوزرنیم>\n"
        "/ban <آیدی>\n"
        "/unban <آیدی>\n"
        "/tickets — تیکت‌های در انتظار\n"
        "/reply <شماره تیکت> <متن>\n"
        "/history <آیدی کاربر> — تاریخچه پیام‌ها"
    )


@admin_only
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = db.get_stats()
    await update.message.reply_text(
        f"👥 کاربرها: {s['users']}\n"
        f"✉️ پیام‌ها: {s['messages']}\n"
        f"🚫 مسدودی‌ها: {s['blocks']}\n"
        f"🆘 تیکت‌های در انتظار: {s['pending_tickets']}"
    )


@admin_only
async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = int(context.args[0]) if context.args else 0
    rows = db.list_users(offset=page * 10, limit=10)
    if not rows:
        await update.message.reply_text("موردی نیست.")
        return
    lines = [f"{'🔴' if r['is_banned'] else '🟢'} {r['id']} — @{r['username'] or '-'}" for r in rows]
    await update.message.reply_text("\n".join(lines))


@admin_only
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استفاده: /search <آیدی یا یوزرنیم>")
        return
    rows = db.search_user(context.args[0])
    if not rows:
        await update.message.reply_text("پیدا نشد.")
        return
    lines = [
        f"{'🔴' if r['is_banned'] else '🟢'} {r['id']} — @{r['username'] or '-'} — {r['created_at']}"
        for r in rows
    ]
    await update.message.reply_text("\n".join(lines))


@admin_only
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استفاده: /ban <آیدی>")
        return
    db.ban_user(int(context.args[0]))
    await update.message.reply_text("مسدود شد.")


@admin_only
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استفاده: /unban <آیدی>")
        return
    db.unban_user(int(context.args[0]))
    await update.message.reply_text("رفع مسدودیت شد.")


@admin_only
async def tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.get_pending_tickets()
    if not rows:
        await update.message.reply_text("تیکت در انتظاری نیست.")
        return
    for t in rows:
        await update.message.reply_text(
            f"🆘 تیکت #{t['id']} از {t['user_id']}:\n{t['message']}\n\nبرای پاسخ: /reply {t['id']} <متن>"
        )


@admin_only
async def reply_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("استفاده: /reply <شماره تیکت> <متن>")
        return
    ticket_id = int(context.args[0])
    text = " ".join(context.args[1:])
    db.reply_ticket(ticket_id, text)
    await update.message.reply_text("پاسخ ثبت شد؛ ظرف چند ثانیه از طریق بات اصلی برای کاربر ارسال می‌شه.")


@admin_only
async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استفاده: /history <آیدی کاربر>")
        return
    user_id = int(context.args[0])
    rows = db.get_user_messages(user_id)
    if not rows:
        await update.message.reply_text("پیامی ثبت نشده.")
        return
    lines = [
        f"[{r['created_at']}] owner={r['owner_id']} sender={r['sender_id']} "
        f"({r['direction']}, {r['content_type']}): {r['text_content'] or ''}"
        for r in rows
    ]
    await update.message.reply_text("\n".join(lines)[:4000])


def main():
    if not ADMIN_TOKEN:
        raise RuntimeError("ADMIN_BOT_TOKEN تنظیم نشده.")

    db.init_db()

    app = ApplicationBuilder().token(ADMIN_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("users", users_list))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("tickets", tickets))
    app.add_handler(CommandHandler("reply", reply_ticket))
    app.add_handler(CommandHandler("history", history))
    app.run_polling()


if __name__ == "__main__":
    main()
