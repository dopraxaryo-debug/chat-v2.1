import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import db

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("BOT_TOKEN")
BOT_USERNAME = os.environ.get("BOT_USERNAME")  # بدون @ - مثلا MyAnonBot

MAIN_MENU = ReplyKeyboardMarkup(
    [["🔗 لینک من"], ["🚫 لیست مسدودی‌ها", "🆘 پشتیبانی"]],
    resize_keyboard=True,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    user = db.get_or_create_user(tg_user.id, tg_user.username)

    if user["is_banned"]:
        await update.message.reply_text("متاسفانه دسترسی شما مسدود شده.")
        return

    args = context.args
    if args:
        token = args[0]
        target = db.get_user_by_token(token)
        if not target:
            await update.message.reply_text("این لینک معتبر نیست.")
            return
        if target["id"] == tg_user.id:
            await update.message.reply_text("این لینک خودته! نمی‌تونی برای خودت پیام ناشناس بفرستی 😄")
            return
        if target["is_banned"]:
            await update.message.reply_text("این کاربر در دسترس نیست.")
            return

        context.user_data["compose_target"] = target["id"]
        context.user_data.pop("reply_to", None)
        context.user_data.pop("support_mode", None)
        await update.message.reply_text("پیامتو بنویس، کاملاً ناشناس براش ارسال می‌شه 🙊")
        return

    await update.message.reply_text(
        "سلام! 👋 با این بات می‌تونی لینک اختصاصی خودتو بسازی و پیام‌های ناشناس بگیری.\n\n"
        "از دکمه‌های پایین استفاده کن.",
        reply_markup=MAIN_MENU,
    )


async def show_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    user = db.get_or_create_user(tg_user.id, tg_user.username)
    link = f"https://t.me/{BOT_USERNAME}?start={user['link_token']}"
    await update.message.reply_text(f"این لینک اختصاصی توئه، هرجا خواستی به اشتراک بذار:\n\n{link}")


async def show_blocked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = update.effective_user.id
    blocked = db.list_blocked(owner_id)
    if not blocked:
        await update.message.reply_text("لیست مسدودی‌هات خالیه.")
        return

    for row in blocked:
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ آزاد کردن", callback_data=f"unblock:{row['sender_id']}")]]
        )
        await update.message.reply_text(f"🚫 ناشناس #{row['anon_number']}", reply_markup=kb)


async def start_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["support_mode"] = True
    context.user_data.pop("compose_target", None)
    context.user_data.pop("reply_to", None)
    await update.message.reply_text(
        "پیامتو برای پشتیبانی بنویس. (این پیام ناشناس نیست، پشتیبانی می‌تونه بهت جواب بده)"
    )


def extract_content(msg):
    if msg.text:
        return "text", msg.text, None
    if msg.photo:
        return "photo", msg.caption, msg.photo[-1].file_id
    if msg.video:
        return "video", msg.caption, msg.video.file_id
    if msg.voice:
        return "voice", msg.caption, msg.voice.file_id
    if msg.sticker:
        return "sticker", None, msg.sticker.file_id
    return "other", msg.caption, None


async def copy_content(context, chat_id, msg):
    await context.bot.copy_message(chat_id=chat_id, from_chat_id=msg.chat_id, message_id=msg.message_id)


async def relay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    user = db.get_or_create_user(tg_user.id, tg_user.username)

    if user["is_banned"]:
        await update.message.reply_text("دسترسی شما مسدود شده.")
        return

    msg = update.message
    content_type, text_content, file_id = extract_content(msg)

    # حالت پاسخ به یه پیام ناشناس خاص
    if context.user_data.get("reply_to"):
        sender_id = context.user_data.pop("reply_to")
        try:
            await context.bot.send_message(sender_id, "↩️ پاسخ به پیامت:")
            await copy_content(context, sender_id, msg)
            db.log_message(tg_user.id, sender_id, "to_sender", content_type, text_content, file_id)
            await update.message.reply_text("پاسخت ارسال شد ✅")
        except Exception:
            await update.message.reply_text("ارسال پاسخ ممکن نشد.")
        return

    # حالت پشتیبانی
    if context.user_data.get("support_mode"):
        context.user_data["support_mode"] = False
        db.create_ticket(tg_user.id, text_content or f"[{content_type}]")
        await update.message.reply_text("پیامت برای پشتیبانی ارسال شد. منتظر پاسخ باش 🙏")
        return

    # حالت ارسال پیام ناشناس به یه نفر (بعد از باز کردن لینک اون شخص)
    target_id = context.user_data.pop("compose_target", None)
    if target_id:
        if db.is_blocked(target_id, tg_user.id):
            await update.message.reply_text("امکان ارسال پیام به این کاربر وجود نداره.")
            return
        anon_num = db.get_anon_number(target_id, tg_user.id)
        try:
            await context.bot.send_message(target_id, f"📩 پیام ناشناس #{anon_num}:")
            await copy_content(context, target_id, msg)
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("↩️ پاسخ", callback_data=f"reply:{tg_user.id}"),
                InlineKeyboardButton("🚫 مسدود کردن", callback_data=f"block:{tg_user.id}"),
            ]])
            await context.bot.send_message(target_id, "برای پاسخ یا مسدود کردن:", reply_markup=kb)
            db.log_message(target_id, tg_user.id, "to_owner", content_type, text_content, file_id)
            await update.message.reply_text("پیامت ناشناس ارسال شد ✅")
        except Exception:
            await update.message.reply_text("این کاربر در دسترس نیست.")
        return

    await update.message.reply_text(
        "برای ارسال پیام ناشناس، از لینک یه نفر استفاده کن. برای گرفتن لینک خودت «🔗 لینک من» رو بزن.",
        reply_markup=MAIN_MENU,
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    owner_id = query.from_user.id
    action, raw_id = query.data.split(":")
    other_id = int(raw_id)

    if action == "reply":
        context.user_data["reply_to"] = other_id
        context.user_data.pop("compose_target", None)
        context.user_data.pop("support_mode", None)
        await query.message.reply_text("پاسخت رو بنویس:")

    elif action == "block":
        db.block_user(owner_id, other_id)
        await query.edit_message_text("🚫 این کاربر مسدود شد.")

    elif action == "unblock":
        db.unblock_user(owner_id, other_id)
        await query.edit_message_text("✅ این کاربر آزاد شد.")


async def deliver_answered_tickets(context: ContextTypes.DEFAULT_TYPE):
    for ticket in db.get_answered_tickets():
        try:
            await context.bot.send_message(ticket["user_id"], f"🆘 پاسخ پشتیبانی:\n\n{ticket['reply']}")
            db.mark_ticket_delivered(ticket["id"])
        except Exception:
            logging.exception("خطا در ارسال پاسخ تیکت %s", ticket["id"])


def main():
    if not TOKEN or not BOT_USERNAME:
        raise RuntimeError("متغیرهای BOT_TOKEN و BOT_USERNAME باید تنظیم شده باشن.")

    db.init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^🔗 لینک من$"), show_link))
    app.add_handler(MessageHandler(filters.Regex("^🚫 لیست مسدودی‌ها$"), show_blocked))
    app.add_handler(MessageHandler(filters.Regex("^🆘 پشتیبانی$"), start_support))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, relay))

    app.job_queue.run_repeating(deliver_answered_tickets, interval=5, first=5)

    app.run_polling()


if __name__ == "__main__":
    main()
