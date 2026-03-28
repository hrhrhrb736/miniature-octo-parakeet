"""
APK Signing Proxy Bot — With Subscription System (FIXED)
=========================================================
Fixes:
  - View Plans button now works correctly from callbacks
  - Unsubscribed user gets full plan info + buy button inline
  - All callback buttons properly edit message in place

Environment variables required:
    BOT_TOKEN, API_ID, API_HASH, SESSION_STRING, SIGNER_BOT, ADMIN_ID
"""

import asyncio, os, json, logging
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)

# ── Credentials from environment — NEVER hardcode ──
BOT_TOKEN      = os.environ["BOT_TOKEN"]
API_ID         = int(os.environ["API_ID"])
API_HASH       = os.environ["API_HASH"]
SESSION_STRING = os.environ["SESSION_STRING"]
SIGNER_BOT     = os.environ.get("SIGNER_BOT", "@apksignerbot")
ADMIN_ID       = int(os.environ["ADMIN_ID"])
CONTACT        = "@im_streak"

PLANS = {
    "1": {"label": "1 Month",  "price": "$130", "days": 30},
    "3": {"label": "3 Months", "price": "$360", "days": 90},
    "6": {"label": "6 Months", "price": "$600", "days": 180},
}

DB_FILE = "subscribers.json"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

pending_requests: dict = {}
user_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)


# ─────────────────────────────────────────────
#  DATABASE HELPERS
# ─────────────────────────────────────────────
def load_db() -> dict:
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data: dict):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)

def is_subscribed(user_id: int) -> bool:
    db = load_db()
    entry = db.get(str(user_id))
    if not entry:
        return False
    return datetime.now() < datetime.fromisoformat(entry["expiry"])

def get_expiry(user_id: int):
    db = load_db()
    entry = db.get(str(user_id))
    return entry["expiry"] if entry else None

def add_subscription(user_id: int, days: int):
    db = load_db()
    key = str(user_id)
    if key in db:
        current = datetime.fromisoformat(db[key]["expiry"])
        base = max(current, datetime.now())
    else:
        base = datetime.now()
    expiry = base + timedelta(days=days)
    db[key] = {"expiry": expiry.isoformat(), "days": days}
    save_db(db)
    return expiry

def revoke_subscription(user_id: int):
    db = load_db()
    db.pop(str(user_id), None)
    save_db(db)


# ─────────────────────────────────────────────
#  REUSABLE MESSAGE BUILDERS
# ─────────────────────────────────────────────
def plans_text() -> str:
    return (
        "💎 *Choose a Subscription Plan*\n\n"
        "┌─────────────────────────────┐\n"
        "│  📅 *1 Month*   →   *$130*        │\n"
        "│  📅 *3 Months*  →   *$360*        │\n"
        "│     _(save $30 vs monthly)_  │\n"
        "│  📅 *6 Months*  →   *$600*        │\n"
        "│     _(save $180 — best deal)_ │\n"
        "└─────────────────────────────┘\n\n"
        "✅ Unlimited APK signing\n"
        "✅ Instant signed APK delivery\n"
        "✅ Priority processing queue\n"
        "✅ 24/7 support via Telegram\n\n"
        f"👉 Contact *{CONTACT}* to purchase\n"
        "_Payment confirms subscription instantly_"
    )

def plans_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📞 Contact to Buy — @im_streak", url="https://t.me/im_streak")],
        [InlineKeyboardButton("◀️ Back to Menu", callback_data="menu")],
    ])

def menu_text(first_name: str) -> str:
    return (
        f"👋 Welcome *{first_name}*!\n\n"
        "I am an *APK Signing Bot*.\n"
        "Send me any `.apk` file and I will get it signed for you instantly.\n\n"
        "🔐 An active subscription is required to use this bot.\n\n"
        "Use the buttons below to get started 👇"
    )

def menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 View Plans & Pricing", callback_data="plans")],
        [InlineKeyboardButton("📋 Check My Subscription", callback_data="status")],
        [InlineKeyboardButton("📞 Contact to Buy", url="https://t.me/im_streak")],
    ])

def no_sub_text() -> str:
    return (
        "🔒 *Subscription Required*\n\n"
        "You do not have an active subscription yet.\n\n"
        "┌─────────────────────────────┐\n"
        "│  📅 *1 Month*   →   *$130*        │\n"
        "│  📅 *3 Months*  →   *$360*        │\n"
        "│     _(save $30)_             │\n"
        "│  📅 *6 Months*  →   *$600*        │\n"
        "│     _(best value — save $180)_ │\n"
        "└─────────────────────────────┘\n\n"
        "✅ Unlimited APK signing\n"
        "✅ Instant delivery after signing\n"
        "✅ Priority queue + 24/7 support\n\n"
        f"💬 To subscribe, message *{CONTACT}* on Telegram\n"
        "_Your access will be activated within minutes of payment_"
    )

def no_sub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📞 Buy Now — @im_streak", url="https://t.me/im_streak")],
        [InlineKeyboardButton("📋 Check My Status", callback_data="status")],
    ])


# ─────────────────────────────────────────────
#  USER COMMANDS
# ─────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        menu_text(user.first_name),
        parse_mode="Markdown",
        reply_markup=menu_keyboard()
    )

async def cmd_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        plans_text(),
        parse_mode="Markdown",
        reply_markup=plans_keyboard()
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_subscribed(user_id):
        exp_dt    = datetime.fromisoformat(get_expiry(user_id))
        days_left = (exp_dt - datetime.now()).days
        await update.message.reply_text(
            f"✅ *Subscription Active*\n\n"
            f"📅 Expires: `{exp_dt.strftime('%d %b %Y')}`\n"
            f"⏳ Days remaining: *{days_left} days*\n\n"
            "Send any `.apk` file and I will sign it for you!",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            no_sub_text(),
            parse_mode="Markdown",
            reply_markup=no_sub_keyboard()
        )


# ─────────────────────────────────────────────
#  CALLBACK BUTTON HANDLER (THE FIXED PART)
# ─────────────────────────────────────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Always answer the callback first — stops the loading spinner on button
    await query.answer()

    user = query.from_user

    if query.data == "plans":
        # Edit the existing message to show plans — no new message needed
        await query.edit_message_text(
            text=plans_text(),
            parse_mode="Markdown",
            reply_markup=plans_keyboard()
        )

    elif query.data == "menu":
        # Go back to main menu
        await query.edit_message_text(
            text=menu_text(user.first_name),
            parse_mode="Markdown",
            reply_markup=menu_keyboard()
        )

    elif query.data == "status":
        user_id = user.id
        if is_subscribed(user_id):
            exp_dt    = datetime.fromisoformat(get_expiry(user_id))
            days_left = (exp_dt - datetime.now()).days
            await query.edit_message_text(
                text=(
                    f"✅ *Subscription Active*\n\n"
                    f"📅 Expires: `{exp_dt.strftime('%d %b %Y')}`\n"
                    f"⏳ Days remaining: *{days_left} days*\n\n"
                    "Send any `.apk` file and I will sign it for you!"
                ),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Back to Menu", callback_data="menu")]
                ])
            )
        else:
            await query.edit_message_text(
                text=no_sub_text(),
                parse_mode="Markdown",
                reply_markup=no_sub_keyboard()
            )


# ─────────────────────────────────────────────
#  ADMIN COMMANDS
# ─────────────────────────────────────────────
async def cmd_grant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/grant <user_id> <1|3|6>"""
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        target_id = int(context.args[0])
        months    = context.args[1]
        plan      = PLANS[months]
        expiry    = add_subscription(target_id, plan["days"])
        await update.message.reply_text(
            f"✅ Granted *{plan['label']}* to `{target_id}`\n"
            f"Expires: `{expiry.strftime('%d %b %Y')}`",
            parse_mode="Markdown"
        )
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"🎉 *Subscription Activated!*\n\n"
                f"Plan: *{plan['label']}* ({plan['price']})\n"
                f"Expires: `{expiry.strftime('%d %b %Y')}`\n\n"
                "✅ You can now send `.apk` files to get them signed!\n"
                "_Just send the file directly in this chat._"
            ),
            parse_mode="Markdown"
        )
    except (IndexError, KeyError, ValueError):
        await update.message.reply_text(
            "❌ Usage: `/grant <user_id> <1|3|6>`\nExample: `/grant 123456789 3`",
            parse_mode="Markdown"
        )

async def cmd_revoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/revoke <user_id>"""
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        target_id = int(context.args[0])
        revoke_subscription(target_id)
        await update.message.reply_text(
            f"✅ Revoked subscription for `{target_id}`",
            parse_mode="Markdown"
        )
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"⚠️ *Subscription Ended*\n\n"
                f"Your subscription has been revoked.\n"
                f"Contact *{CONTACT}* to renew your plan."
            ),
            parse_mode="Markdown"
        )
    except (IndexError, ValueError):
        await update.message.reply_text(
            "❌ Usage: `/revoke <user_id>`",
            parse_mode="Markdown"
        )

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/list — show all subscribers"""
    if update.effective_user.id != ADMIN_ID:
        return
    db = load_db()
    if not db:
        await update.message.reply_text("📭 No subscribers yet.")
        return
    lines = ["📋 *All Subscribers:*\n"]
    for uid, info in db.items():
        exp       = datetime.fromisoformat(info["expiry"])
        days_left = (exp - datetime.now()).days
        icon      = "✅" if days_left > 0 else "❌"
        lines.append(f"{icon} `{uid}` — `{exp.strftime('%d %b %Y')}` ({days_left}d left)")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ─────────────────────────────────────────────
#  APK HANDLER
# ─────────────────────────────────────────────
async def handle_user_apk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id  = update.effective_user.id
    document = update.message.document

    # ── Not subscribed → show full plan info ──
    if not is_subscribed(user_id):
        await update.message.reply_text(
            no_sub_text(),
            parse_mode="Markdown",
            reply_markup=no_sub_keyboard()
        )
        return

    # ── Not an APK ──
    if not document.file_name.lower().endswith(".apk"):
        await update.message.reply_text(
            "❌ Please send a valid `.apk` file.\n"
            "_Only APK files are supported._",
            parse_mode="Markdown"
        )
        return

    # ── Subscribed — process the APK ──
    status_msg = await update.message.reply_text(
        f"📦 *Received:* `{document.file_name}`\n"
        "⏳ Downloading and forwarding to signer...\n"
        "_This usually takes 10–30 seconds._",
        parse_mode="Markdown"
    )

    file       = await context.bot.get_file(document.file_id)
    local_path = f"/tmp/{document.file_id}_{document.file_name}"
    await file.download_to_drive(local_path)
    await send_to_signer_bot(user_id, local_path, document.file_name)


async def send_to_signer_bot(user_id: int, file_path: str, filename: str):
    try:
        sent = await user_client.send_file(
            SIGNER_BOT,
            file_path,
            caption=f"Sign: {filename}"
        )
        pending_requests[sent.id] = {"user_id": user_id, "filename": filename}
        logger.info(f"Sent to signer | msg={sent.id} | user={user_id}")
    except Exception as e:
        logger.error(f"Error sending to signer: {e}")
        bot = Bot(BOT_TOKEN)
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"❌ *Failed to reach the signer bot.*\n\n"
                f"Error: `{e}`\n\n"
                "Please try again in a moment."
            ),
            parse_mode="Markdown"
        )
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


# ─────────────────────────────────────────────
#  RECEIVE SIGNED APK FROM SIGNER BOT
# ─────────────────────────────────────────────
@user_client.on(events.NewMessage(from_users=SIGNER_BOT))
async def handle_signer_reply(event):
    bot = Bot(BOT_TOKEN)

    if event.document:
        if not pending_requests:
            logger.warning("Received signed APK but no pending requests.")
            return
        latest_key  = max(pending_requests.keys())
        req         = pending_requests.pop(latest_key)
        signed_path = f"/tmp/signed_{event.document.id}.apk"
        await event.download_media(signed_path)
        await bot.send_document(
            chat_id=req["user_id"],
            document=open(signed_path, "rb"),
            filename=f"signed_{req['filename']}",
            caption=(
                "✅ *Your APK has been signed successfully!*\n\n"
                f"📄 File: `signed_{req['filename']}`\n"
                "_Download and install it on your device._"
            ),
            parse_mode="Markdown"
        )
        logger.info(f"Delivered signed APK to user {req['user_id']}")
        if os.path.exists(signed_path):
            os.remove(signed_path)

    elif event.text and pending_requests:
        latest_key = max(pending_requests.keys())
        req = pending_requests.get(latest_key)
        if req:
            await bot.send_message(
                chat_id=req["user_id"],
                text=f"ℹ️ *Signer bot update:*\n{event.text}",
                parse_mode="Markdown"
            )


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
async def main():
    await user_client.connect()
    logger.info("✅ Telethon session connected!")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("plans",  cmd_plans))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("grant",  cmd_grant))
    app.add_handler(CommandHandler("revoke", cmd_revoke))
    app.add_handler(CommandHandler("list",   cmd_list))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_user_apk))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    logger.info("🤖 APK Signing Bot is live!")

    await user_client.run_until_disconnected()

    await app.updater.stop()
    await app.stop()
    await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
