"""
CampusConnect — Directory & Discovery
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
import database as db
from utils import (
    format_profile_card, format_profile_summary,
    profile_action_keyboard, pagination_keyboard,
    cancel_keyboard, main_menu_keyboard, check_rate_limit
)

PAGE_SIZE = 5


def require_registration(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user = db.get_user(user_id)
        if not user:
            await update.effective_message.reply_text(
                "❌ You need to register first!\nSend /start to create your profile."
            )
            return
        if user['is_blacklisted']:
            await update.effective_message.reply_text("❌ Your account has been suspended.")
            return
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper


async def _send_user_page(update, users, page, total, prefix, header=""):
    if not users:
        await update.effective_message.reply_text("😕 No students found matching that search.")
        return

    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    msg = header + f"📋 *Results* (page {page+1}/{total_pages}, {total} total)\n\n"
    for i, u in enumerate(users, 1):
        msg += f"*{i + page*PAGE_SIZE}.* {format_profile_summary(u)}\n\n"

    nav = pagination_keyboard(page, total_pages, prefix)
    await update.effective_message.reply_text(msg, parse_mode="Markdown", reply_markup=nav)


@require_registration
async def cmd_directory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = 0
    users = db.search_users(limit=PAGE_SIZE, offset=0)
    total = db.count_users()
    await _send_user_page(update, users, page, total, "dir", "📚 *Student Directory*\n\n")


@require_registration
async def cmd_findbyschool(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        db.set_state(update.effective_user.id, "find:school", {})
        await update.message.reply_text("🏫 Enter school name to search (e.g. EKSU):", reply_markup=cancel_keyboard())
        return
    school = " ".join(args)
    users = db.search_users(school=school, limit=PAGE_SIZE)
    total = db.count_users(school=school)
    await _send_user_page(update, users, 0, total, f"fschool:{school}", f"🏫 *Students at {school.upper()}*\n\n")


@require_registration
async def cmd_findbydept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        db.set_state(update.effective_user.id, "find:dept", {})
        await update.message.reply_text("📚 Enter department to search:", reply_markup=cancel_keyboard())
        return
    dept = " ".join(args)
    users = db.search_users(dept=dept, limit=PAGE_SIZE)
    total = db.count_users(dept=dept)
    await _send_user_page(update, users, 0, total, f"fdept:{dept}", f"📚 *Students in {dept}*\n\n")


@require_registration
async def cmd_findbystate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        db.set_state(update.effective_user.id, "find:state", {})
        await update.message.reply_text("📍 Enter state to search (e.g. Lagos):", reply_markup=cancel_keyboard())
        return
    state = " ".join(args)
    users = db.search_users(state=state, limit=PAGE_SIZE)
    total = db.count_users(state=state)
    await _send_user_page(update, users, 0, total, f"fstate:{state}", f"📍 *Students from {state}*\n\n")


@require_registration
async def cmd_findbyinterest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        db.set_state(update.effective_user.id, "find:interest", {})
        await update.message.reply_text("🌟 Enter interest to search (e.g. Tech, Music):", reply_markup=cancel_keyboard())
        return
    interest = " ".join(args)
    users = db.search_users(interest=interest, limit=PAGE_SIZE)
    total = db.count_users()
    await _send_user_page(update, users, 0, total, f"fint:{interest}", f"🌟 *Students interested in {interest}*\n\n")


@require_registration
async def cmd_saved(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    saved = db.get_saved(user_id)
    if not saved:
        await update.message.reply_text("🔖 You haven't saved any profiles yet.\n\nBrowse /directory and tap Save on profiles you like!")
        return
    msg = "🔖 *Your Saved Profiles*\n\n"
    for u in saved:
        msg += f"👤 *{u['full_name']}*\n🎓 {u['school']} · {u['level']}\n\n"
    await update.message.reply_text(msg, parse_mode="Markdown")


@require_registration
async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("❌ Usage: /report @username or /report [user_id]")
        return
    db.set_state(update.effective_user.id, "report:reason", {'target': args[0]})
    await update.message.reply_text(
        f"🚩 *Report User: {args[0]}*\n\nWhat's the reason for this report?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([
            ["Fake Profile", "Spam"],
            ["Harassment", "Scam"],
            ["Other"]
        ], resize_keyboard=True, one_time_keyboard=True)
    )


async def handle_directory_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if not check_rate_limit(user_id, "callback", 20):
        await query.answer("⏳ Slow down!", show_alert=True)
        return

    # CONNECT
    if data.startswith("connect:"):
        target_id = int(data.split(":")[1])
        target = db.get_user(target_id)
        if not target:
            await query.answer("User not found.", show_alert=True)
            return
        if target_id == user_id:
            await query.answer("You can't connect with yourself!", show_alert=True)
            return
        requester = db.get_user(user_id)
        # Send contact card to both parties
        card = format_profile_card(requester)
        try:
            await context.bot.send_message(
                target_id,
                f"📲 *New Connection Request!*\n\n{card}\n\n_They want to connect with you!_",
                parse_mode="Markdown"
            )
            target_card = format_profile_card(target)
            await context.bot.send_message(
                user_id,
                f"✅ *Contact Card Sent!*\n\nHere's {target['full_name']}'s details:\n\n{target_card}",
                parse_mode="Markdown"
            )
        except Exception:
            await query.answer("Could not send message. User may have blocked the bot.", show_alert=True)
            return
        await query.answer("✅ Contact cards exchanged!")

    # SAVE
    elif data.startswith("save:"):
        target_id = int(data.split(":")[1])
        db.save_profile(user_id, target_id)
        await query.answer("🔖 Profile saved!")

    # REPORT
    elif data.startswith("report:"):
        target_id = int(data.split(":")[1])
        db.set_state(user_id, "report:reason", {'target_id': target_id})
        await query.message.reply_text(
            "🚩 Why are you reporting this profile?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Fake Profile", callback_data=f"reportr:{target_id}:fake")],
                [InlineKeyboardButton("Spam", callback_data=f"reportr:{target_id}:spam")],
                [InlineKeyboardButton("Harassment", callback_data=f"reportr:{target_id}:harassment")],
                [InlineKeyboardButton("Scam", callback_data=f"reportr:{target_id}:scam")],
            ])
        )

    elif data.startswith("reportr:"):
        _, target_id, reason = data.split(":")
        requester = db.get_user(user_id)
        db.create_report(user_id, int(target_id), reason)
        db.clear_state(user_id)
        await query.answer("🚩 Report submitted. Thank you!")
        await query.message.reply_text("✅ Report received. Our team will review it.")

    # PAGINATION
    elif ":page:" in data:
        parts = data.split(":page:")
        prefix = parts[0]
        page = int(parts[1])

        school = dept = state = interest = None
        if prefix.startswith("fschool:"):
            school = prefix.split("fschool:")[1]
        elif prefix.startswith("fdept:"):
            dept = prefix.split("fdept:")[1]
        elif prefix.startswith("fstate:"):
            state = prefix.split("fstate:")[1]
        elif prefix.startswith("fint:"):
            interest = prefix.split("fint:")[1]

        users = db.search_users(school=school, dept=dept, state=state, interest=interest,
                                 limit=PAGE_SIZE, offset=page * PAGE_SIZE)
        total = db.count_users(school=school, dept=dept, state=state)
        total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE

        msg = f"📋 *Results* (page {page+1}/{total_pages}, {total} total)\n\n"
        for i, u in enumerate(users, 1):
            msg += f"*{i + page*PAGE_SIZE}.* {format_profile_summary(u)}\n\n"

        nav = pagination_keyboard(page, total_pages, prefix)
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=nav)
