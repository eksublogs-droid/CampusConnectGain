"""
CampusConnect — Main Bot
53-task full build: registration, directory, ads, drops, marketplace, admin
"""
import os
import logging
from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

load_dotenv()
logging.basicConfig(format="%(asctime)s — %(name)s — %(levelname)s — %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Import all handlers ──
import database as db
from handlers.registration import start_registration, handle_registration_step, handle_web_app_data
from handlers.profile import cmd_myprofile, cmd_edit, handle_edit_flow
from handlers.directory import (
    cmd_directory, cmd_findbyschool, cmd_findbydept,
    cmd_findbystate, cmd_findbyinterest, cmd_saved,
    cmd_report, handle_directory_callback
)
from handlers.ads import cmd_runad, cmd_myadstatus, handle_ad_callback, handle_ad_message
from handlers.store import cmd_store, cmd_myorders, handle_store_callback, handle_custom_order_message
from handlers.drops import cmd_contactdrop, cmd_drophistory, cmd_dropstats, handle_drop_callback
from admin import (
    cmd_stats, cmd_broadcast, cmd_lookup, cmd_approve, cmd_remove,
    cmd_blacklist, cmd_revenue, cmd_export, cmd_adqueue, cmd_orders,
    cmd_fulfillorder, cmd_rundrop, handle_admin_callback, handle_admin_message
)
from utils import main_menu_keyboard, format_reg_channel_post


# ─────────────────────────────────────
# CORE HANDLERS
# ─────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if user and not user['is_blacklisted']:
        from utils import format_profile_card
        card = format_profile_card(user)
        await update.message.reply_text(
            f"👋 Welcome back, *{user['full_name']}!*\n\n{card}\n\n"
            f"What would you like to do?",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )
        return
    await start_registration(update, context)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *CampusConnect — Command Guide*\n\n"
        "👤 *Profile*\n"
        "/start — Register or see welcome\n"
        "/myprofile — View your profile\n"
        "/edit — Update any profile field\n\n"
        "🔍 *Discovery*\n"
        "/directory — Browse all students\n"
        "/findbyschool — Search by school\n"
        "/findbydept — Search by department\n"
        "/findbystate — Search by state\n"
        "/findbyinterest — Search by interest\n"
        "/saved — Your saved profiles\n"
        "/report — Flag a fake profile\n\n"
        "📢 *Visibility & Ads*\n"
        "/runad — Run a paid ad on the channel\n"
        "/myadstatus — Track your active ads\n\n"
        "🛒 *Marketplace*\n"
        "/store — Browse contact packs, tools & more\n"
        "/myorders — Your order history\n\n"
        "📬 *Contact Drop*\n"
        "/contactdrop — Subscribe to VCF drops\n"
        "/drophistory — See your past drops\n\n"
        "ℹ️ *Other*\n"
        "/help — This message",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.clear_state(update.effective_user.id)
    await update.message.reply_text("✅ Cancelled.", reply_markup=main_menu_keyboard())


# ─────────────────────────────────────
# MESSAGE ROUTER
# ─────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    text = update.message.text

    # Check rate limit
    from utils import check_rate_limit
    if not check_rate_limit(user_id, "message", 30):
        await update.message.reply_text("⏳ Too many messages. Please slow down.")
        return

    # Menu shortcuts
    if text == "📋 My Profile":
        return await cmd_myprofile(update, context)
    elif text == "✏️ Edit Profile":
        return await cmd_edit(update, context)
    elif text == "🔍 Find Students":
        return await update.message.reply_text(
            "🔍 *Find Students*\n\nSearch by:\n"
            "• /findbyschool\n• /findbydept\n• /findbystate\n• /findbyinterest",
            parse_mode="Markdown"
        )
    elif text == "📚 Directory":
        return await cmd_directory(update, context)
    elif text == "🛒 Store":
        return await cmd_store(update, context)
    elif text == "📬 Contact Drop":
        return await cmd_contactdrop(update, context)
    elif text == "📢 Run Ad":
        return await cmd_runad(update, context)
    elif text == "🔖 Saved":
        return await cmd_saved(update, context)
    elif text == "ℹ️ Help":
        return await cmd_help(update, context)

    # Check current state for flow handlers
    state, data = db.get_state(user_id)

    if state and state.startswith("reg:"):
        result = await handle_registration_step(update, context)
        if isinstance(result, tuple) and len(result) == 2:
            # Registration complete, post to channel
            new_user = result[1]
            await post_to_channel(new_user, context)
        return

    if state and state.startswith("edit:"):
        if await handle_edit_flow(update, context):
            return

    if state and state.startswith("ad:"):
        if await handle_ad_message(update, context):
            return

    if state and state == "custom_order:describe":
        if await handle_custom_order_message(update, context):
            return

    if state and state.startswith("admin:"):
        if await handle_admin_message(update, context):
            return

    if state and state.startswith("report:"):
        if await handle_report_text(update, context, state, data):
            return

    if state and state.startswith("find:"):
        if await handle_find_text(update, context, state):
            return

    # Default — show menu
    if not db.get_user(user_id):
        await update.message.reply_text("👋 Send /start to join CampusConnect!")
    else:
        await update.message.reply_text(
            "Use the menu below or type /help to see all commands.",
            reply_markup=main_menu_keyboard()
        )


async def handle_report_text(update, context, state, data):
    user_id = update.effective_user.id
    if state == "report:reason":
        reason = update.message.text.strip()
        target = data.get('target') or str(data.get('target_id', ''))
        db.create_report(user_id, data.get('target_id') or 0, reason)
        db.clear_state(user_id)

        admin_ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
        reporter = db.get_user(user_id)
        for admin_id in admin_ids:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"🚩 *New Report*\n\nReporter: {reporter['full_name']} ({user_id})\nTarget: {target}\nReason: {reason}",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

        await update.message.reply_text(
            "✅ Report submitted. Our team will review it.",
            reply_markup=main_menu_keyboard()
        )
        return True
    return False


async def handle_find_text(update, context, state):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text == "❌ Cancel":
        db.clear_state(user_id)
        await update.message.reply_text("Cancelled.", reply_markup=main_menu_keyboard())
        return True

    from handlers.directory import _send_user_page
    PAGE_SIZE = 5

    if state == "find:school":
        users = db.search_users(school=text, limit=PAGE_SIZE)
        total = db.count_users(school=text)
        db.clear_state(user_id)
        await _send_user_page(update, users, 0, total, f"fschool:{text}", f"🏫 *Students at {text.upper()}*\n\n")
        return True

    elif state == "find:dept":
        users = db.search_users(dept=text, limit=PAGE_SIZE)
        total = db.count_users(dept=text)
        db.clear_state(user_id)
        await _send_user_page(update, users, 0, total, f"fdept:{text}", f"📚 *Students in {text}*\n\n")
        return True

    elif state == "find:state":
        users = db.search_users(state=text, limit=PAGE_SIZE)
        total = db.count_users(state=text)
        db.clear_state(user_id)
        await _send_user_page(update, users, 0, total, f"fstate:{text}", f"📍 *Students from {text}*\n\n")
        return True

    elif state == "find:interest":
        users = db.search_users(interest=text, limit=PAGE_SIZE)
        total = db.count_users()
        db.clear_state(user_id)
        await _send_user_page(update, users, 0, total, f"fint:{text}", f"🌟 *Students into {text}*\n\n")
        return True

    return False


async def post_to_channel(user, context):
    channel_id = os.getenv("CHANNEL_ID")
    if not channel_id:
        return
    try:
        text = format_reg_channel_post(user)
        if user.get('profile_photo_id'):
            await context.bot.send_photo(channel_id, user['profile_photo_id'], caption=text, parse_mode="Markdown")
        else:
            await context.bot.send_message(channel_id, text, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Channel post failed: {e}")


# ─────────────────────────────────────
# CALLBACK ROUTER
# ─────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data.startswith("connect:") or data.startswith("save:") or data.startswith("report") or ":page:" in data:
        await handle_directory_callback(update, context)
    elif data.startswith("adtier:") or data.startswith("ad:"):
        await handle_ad_callback(update, context)
    elif data.startswith("store:") or data.startswith("buyitem:") or data.startswith("verifyorder:") or data.startswith("iteminfo:"):
        await handle_store_callback(update, context)
    elif data.startswith("drop:"):
        await handle_drop_callback(update, context)
    elif data.startswith("admin:"):
        await handle_admin_callback(update, context)
    elif data == "profile:edit":
        await cmd_edit(update, context)
    else:
        await query.answer("Action not recognized.", show_alert=True)


# ─────────────────────────────────────
# BOT COMMANDS SETUP
# ─────────────────────────────────────

async def set_bot_commands(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Register or view welcome"),
        BotCommand("myprofile", "View your profile"),
        BotCommand("edit", "Update your profile"),
        BotCommand("directory", "Browse student directory"),
        BotCommand("findbyschool", "Find students by school"),
        BotCommand("findbydept", "Find students by department"),
        BotCommand("findbystate", "Find students by state"),
        BotCommand("findbyinterest", "Find students by interest"),
        BotCommand("saved", "Your saved profiles"),
        BotCommand("runad", "Run a paid ad"),
        BotCommand("myadstatus", "Track your ads"),
        BotCommand("store", "Browse the marketplace"),
        BotCommand("myorders", "Your order history"),
        BotCommand("contactdrop", "Subscribe to contact drops"),
        BotCommand("drophistory", "Your drop history"),
        BotCommand("report", "Report a fake profile"),
        BotCommand("help", "Show all commands"),
        BotCommand("cancel", "Cancel current action"),
    ])
    print("✅ Bot commands menu set")


# ─────────────────────────────────────
# BOT RUNNER (background thread)
# ─────────────────────────────────────

def run_bot():
    import asyncio
    asyncio.set_event_loop(asyncio.new_event_loop())

    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN not set in environment!")

    # Initialize DB
    db.init_db()
    db.run_migrations()

    # ── Post-init hook ──
    async def post_init(application):
        await set_bot_commands(application)
        from scheduler import start_scheduler
        start_scheduler(application.bot)
        print("🚀 CampusConnect Bot is LIVE!")

    # Build app
    app = Application.builder().token(token).post_init(post_init).build()

    # ── Command Handlers ──
    # User commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("myprofile", cmd_myprofile))
    app.add_handler(CommandHandler("edit", cmd_edit))
    app.add_handler(CommandHandler("directory", cmd_directory))
    app.add_handler(CommandHandler("findbyschool", cmd_findbyschool))
    app.add_handler(CommandHandler("findbydept", cmd_findbydept))
    app.add_handler(CommandHandler("findbystate", cmd_findbystate))
    app.add_handler(CommandHandler("findbyinterest", cmd_findbyinterest))
    app.add_handler(CommandHandler("saved", cmd_saved))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("runad", cmd_runad))
    app.add_handler(CommandHandler("myadstatus", cmd_myadstatus))
    app.add_handler(CommandHandler("store", cmd_store))
    app.add_handler(CommandHandler("myorders", cmd_myorders))
    app.add_handler(CommandHandler("contactdrop", cmd_contactdrop))
    app.add_handler(CommandHandler("drophistory", cmd_drophistory))
    app.add_handler(CommandHandler("dropstats", cmd_dropstats))

    # Admin commands
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("lookup", cmd_lookup))
    app.add_handler(CommandHandler("approve", cmd_approve))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("blacklist", cmd_blacklist))
    app.add_handler(CommandHandler("revenue", cmd_revenue))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("adqueue", cmd_adqueue))
    app.add_handler(CommandHandler("orders", cmd_orders))
    app.add_handler(CommandHandler("fulfillorder", cmd_fulfillorder))
    app.add_handler(CommandHandler("rundrop", cmd_rundrop))

    # ── Callback Handler ──
    app.add_handler(CallbackQueryHandler(handle_callback))

    # ── Web App Data Handler (Mini App form submission) ──
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))

    # ── Message Handler ──
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Starting CampusConnect Bot...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


# ─────────────────────────────────────
# MAIN — Flask is the main process
# ─────────────────────────────────────

def main():
    import threading
    from webhook import app as flask_app

    # Start bot in background thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    print("🤖 Bot thread started")

    # Flask runs as main process so Railway binds to it properly
    port = int(os.getenv("PORT", 8080))
    print(f"🌐 Starting Flask on port {port}")
    flask_app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
