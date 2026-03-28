"""
APK Signing Proxy Bot — With Subscription System
==================================================
Flow: User → subscription check → Your Bot → Signer Bot → User

Environment variables required:
    BOT_TOKEN, API_ID, API_HASH, SESSION_STRING,
    SIGNER_BOT, ADMIN_ID
"""

import asyncio, os, json, logging
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)

# ── Credentials from environment (NEVER hardcode) ──
BOT_TOKEN      = os.environ["BOT_TOKEN"]
API_ID         = int(os.environ["API_ID"])
API_HASH       = os.environ["API_HASH"]
SESSION_STRING = os.environ["SESSION_STRING"]
SIGNER_BOT     = os.environ.get("SIGNER_BOT", "@apksignerbot")
ADMIN_ID       = int(os.environ["ADMIN_ID"])   # Your Telegram user ID
CONTACT        = "@im_streak"

# ── Subscription prices ──
PLANS = {
    "1": {"label": "1 Month",  "price": "$130", "days": 30},
    "3": {"label": "3 Months", "price": "$360", "days": 90},
    "6": {"label": "6 Months", "price": "$600", "days": 180},
}

# ── Simple JSON file as database ──
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
    expiry = datetime.fromisoformat(entry["expiry"])
    return datetime.now() < expiry

def get_expiry(user_id: int) -> str:
    db = load_db()
    entry = db.get(str(user_id))
    if not entry:
        return None
    return entry["expiry"]

def add_subscription(user_id: int, days: int):
    db = load_db()
    key = str(user_id)
    # Extend if already subscribed, else start fresh
    if key in db:
        current = datetime.fromisoformat(db[key]["expiry"])
        base = max(current, datetime.now())
    else:
        base = datetime.now()
    expiry = base + timedelta(days=days)
    db[key] = {"expiry": expiry.isoformat(), "added_days": days}
    save_db(db)
    return expiry

def revoke_subscription(user_id: int):
    db = load_db()
    db.pop(str(user_id), None)
    save_db(db)


# ─────────────────────────────────────────────
#  USER COMMANDS
# ─────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    kb = [
        [InlineKeyboardButton("💎 View Plans", callback_data="plans")],
        [InlineKeyboardButton("📋 My Status",  callback_data="status")],
        [InlineKeyboardButton("📞 Contact to Buy", url=f"https://t.me/im_streak")],
    ]
    await update.message.reply_text(
        f"👋 Welcome *{user.first_name}*!\n\n"
        "I'm an *APK Signing Bot*. Send me any `.apk` file and I'll get it signed instantly.\n\n"
        "You need an active subscription to use this bot.\n"
        "Use the buttons below to get started.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_subscribed(user_id):
        expiry = get_expiry(user_id)
        exp_dt = datetime.fromisoformat(expiry)
        days_left = (exp_dt - datetime.now()).days
        await update.message.reply_text(
            f"✅ *Subscription Active*\n\n"
            f"Expires: `{exp_dt.strftime('%d %b %Y')}`\n"
            f"Days remaining: *{days_left} days*",
            parse_mode="Markdown"
        )
    else:
        kb = [[InlineKeyboardButton("💎 View Plans", callback_data="plans")]]
        await update.message.reply_text(
            "❌ *No active subscription.*\n\n"
            "Purchase a plan to start signing APKs.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )

async def cmd_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_plans(update.message)

async def show_plans(target):
    text = (
        "💎 *Subscription Plans*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📅 *1 Month* — $130\n"
        "📅 *3 Months* — $360  _(save $30)_\n"
        "📅 *6 Months* — $600  _(save $180 — best value)_\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "✅ Unlimited APK signing\n"
        "✅ Instant delivery\n"
        "✅ Priority queue\n"
        "✅ Dedicated support\n\n"
        f"To subscribe, contact 👉 {CONTACT}"
    )
    kb = [[InlineKeyboardButton("📞 Contact to Buy", url="https://t.me/im_streak")]]
    await target.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


# ─────────────────────────────────────────────
#  CALLBACK BUTTONS
# ─────────────────────────────────────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "plans":
        await show_plans(query.message)
    elif query.data == "status":
        user_id = query.from_user.id
        if is_subscribed(user_id):
            expiry = get_expiry(user_id)
            exp_dt = datetime.fromisoformat(expiry)
            days_left = (exp_dt - datetime.now()).days
            await query.message.reply_text(
                f"✅ *Subscription Active*\n"
                f"Expires: `{exp_dt.strftime('%d %b %Y')}`\n"
                f"Days left: *{days_left}*",
                parse_mode="Markdown"
            )
        else:
            kb = [[InlineKeyboardButton("💎 View Plans", callback_data="plans")]]
            await query.message.reply_text(
                "❌ *No active subscription.*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb)
            )


# ─────────────────────────────────────────────
#  ADMIN COMMANDS
# ─────────────────────────────────────────────
async def cmd_grant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin only: /grant <user_id> <1|3|6>"""
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        target_id = int(context.args[0])
        months    = context.args[1]
        plan      = PLANS[months]
        expiry    = add_subscription(target_id, plan["days"])
        await update.message.reply_text(
            f"✅ Granted *{plan['label']}* subscription to `{target_id}`\n"
            f"Expires: `{expiry.strftime('%d %b %Y')}`",
            parse_mode="Markdown"
        )
        # Notify the user
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"🎉 *Subscription Activated!*\n\n"
                f"Plan: *{plan['label']}* ({plan['price']})\n"
                f"Expires: `{expiry.strftime('%d %b %Y')}`\n\n"
                "You can now send APK files to get them signed!"
            ),
            parse_mode="Markdown"
        )
    except (IndexError, KeyError, ValueError):
        await update.message.reply_text(
            "Usage: `/grant <user_id> <1|3|6>`\nExample: `/grant 123456789 3`",
            parse_mode="Markdown"
        )

async def cmd_revoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin only: /revoke <user_id>"""
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        target_id = int(context.args[0])
        revoke_subscription(target_id)
        await update.message.reply_text(f"✅ Revoked subscription for `{target_id}`", parse_mode="Markdown")
        await context.bot.send_message(
            chat_id=target_id,
            text="⚠️ Your subscription has been revoked. Contact @im_streak to renew."
        )
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: `/revoke <user_id>`", parse_mode="Markdown")

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin only: /list — show all active subscribers"""
    if update.effective_user.id != ADMIN_ID:
        return
    db = load_db()
    if not db:
        await update.message.reply_text("No subscribers yet.")
        return
    lines = ["📋 *Active Subscribers:*\n"]
    for uid, info in db.items():
        exp = datetime.fromisoformat(info["expiry"])
        days_left = (exp - datetime.now()).days
        status = "✅" if days_left > 0 else "❌"
        lines.append(f"{status} `{uid}` — expires `{exp.strftime('%d %b %Y')}` ({days_left}d left)")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ─────────────────────────────────────────────
#  APK HANDLER
# ─────────────────────────────────────────────
async def handle_user_apk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id  = update.effective_user.id
    document = update.message.document

    # ── Subscription check ──
    if not is_subscribed(user_id):
        kb = [
            [InlineKeyboardButton("💎 View Plans", callback_data="plans")],
            [InlineKeyboardButton("📞 Buy Now", url="https://t.me/im_streak")],
        ]
        await update.message.reply_text(
            "🔒 *Subscription Required*\n\n"
            "You need an active subscription to sign APKs.\n"
            f"Contact {CONTACT} to purchase a plan.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if not document.file_name.lower().endswith(".apk"):
        await update.message.reply_text("❌ Please send a valid `.apk` file.", parse_mode="Markdown")
        return

    msg = await update.message.reply_text(
        f"📦 Received *{document.file_name}*\n⏳ Forwarding to signer... please wait.",
        parse_mode="Markdown"
    )

    file       = await context.bot.get_file(document.file_id)
    local_path = f"/tmp/{document.file_id}_{document.file_name}"
    await file.download_to_drive(local_path)
    await send_to_signer_bot(user_id, local_path, document.file_name)


async def send_to_signer_bot(user_id: int, file_path: str, filename: str):
    try:
        sent = await user_client.send_file(SIGNER_BOT, file_path, caption=f"Sign: {filename}")
        pending_requests[sent.id] = {"user_id": user_id, "filename": filename}
        logger.info(f"Sent to signer | msg={sent.id} | user={user_id}")
    except Exception as e:
        bot = Bot(BOT_TOKEN)
        await bot.send_message(chat_id=user_id, text=f"❌ Error contacting signer bot:\n{e}")
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
            return
        latest_key  = max(pending_requests.keys())
        req         = pending_requests.pop(latest_key)
        signed_path = f"/tmp/signed_{event.document.id}.apk"
        await event.download_media(signed_path)
        await bot.send_document(
            chat_id=req["user_id"],
            document=open(signed_path, "rb"),
            filename=f"signed_{req['filename']}",
            caption="✅ *Your APK has been signed successfully!*",
            parse_mode="Markdown"
        )
        logger.info(f"Delivered signed APK to user {req['user_id']}")
        if os.path.exists(signed_path):
            os.remove(signed_path)

    elif event.text and pending_requests:
        latest_key = max(pending_requests.keys())
        req = pending_requests.get(latest_key)
        if req:
            await bot.send_message(chat_id=req["user_id"], text=f"ℹ️ Signer bot: {event.text}")


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
async def main():
    await user_client.connect()
    logger.info("✅ Telethon connected!")

    app = Application.builder().token(BOT_TOKEN).build()

    # User commands
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("plans",  cmd_plans))

    # Admin commands
    app.add_handler(CommandHandler("grant",  cmd_grant))
    app.add_handler(CommandHandler("revoke", cmd_revoke))
    app.add_handler(CommandHandler("list",   cmd_list))

    # Buttons
    app.add_handler(CallbackQueryHandler(handle_callback))

    # APK files
    app.add_handler(MessageHandler(filters.Document.ALL, handle_user_apk))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    logger.info("🤖 Bot is live with subscription system!")

    await user_client.run_until_disconnected()

    await app.updater.stop()
    await app.stop()
    await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
