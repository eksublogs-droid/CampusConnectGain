"""
CampusConnect — Registration Flow (8 steps)
"""
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
import database as db
from utils import (
    NIGERIAN_STATES, LEVELS, INTERESTS,
    validate_phone, format_profile_card,
    states_keyboard, levels_keyboard, interests_keyboard,
    cancel_keyboard, main_menu_keyboard
)

STEPS = ["full_name", "phone", "school", "department", "level", "state", "interests", "bio"]


async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    existing = db.get_user(user_id)
    if existing and existing['is_blacklisted']:
        await update.message.reply_text("❌ Your account has been suspended. Contact support.")
        return
    if existing:
        await update.message.reply_text(
            f"✅ You're already registered, {existing['full_name']}!\n\n"
            f"Use /myprofile to view your profile or /edit to update it.",
            reply_markup=main_menu_keyboard()
        )
        return

    db.set_state(user_id, "reg:full_name", {})
    await update.message.reply_text(
        "🎓 *Welcome to CampusConnect!*\n\n"
        "Nigeria's student network — right inside Telegram.\n\n"
        "Let's set up your profile in 8 quick steps.\n\n"
        "👤 *Step 1 of 8 — Full Name*\nWhat's your full name?",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )


async def handle_registration_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text == "❌ Cancel":
        db.clear_state(user_id)
        await update.message.reply_text("Registration cancelled.", reply_markup=main_menu_keyboard())
        return

    state, data = db.get_state(user_id)
    if not state or not state.startswith("reg:"):
        return False  # not in registration

    step = state.split("reg:")[1]

    # ── STEP 1: Full Name ──
    if step == "full_name":
        if len(text) < 3 or len(text) > 60:
            await update.message.reply_text("❌ Name must be 3–60 characters. Try again:")
            return True
        data['full_name'] = text
        db.set_state(user_id, "reg:phone", data)
        await update.message.reply_text(
            "📱 *Step 2 of 8 — Phone Number*\nEnter your WhatsApp number (e.g. 08012345678):",
            parse_mode="Markdown"
        )

    # ── STEP 2: Phone ──
    elif step == "phone":
        phone = validate_phone(text)
        if not phone:
            await update.message.reply_text("❌ Invalid number. Use format: 08012345678 or 234801...")
            return True
        data['phone'] = phone
        db.set_state(user_id, "reg:school", data)
        await update.message.reply_text(
            "🏫 *Step 3 of 8 — School*\nType your university or polytechnic name:\n_(e.g. EKSU, UNILAG, LASU)_",
            parse_mode="Markdown"
        )

    # ── STEP 3: School ──
    elif step == "school":
        if len(text) < 2 or len(text) > 80:
            await update.message.reply_text("❌ School name too short/long. Try again:")
            return True
        data['school'] = text.upper()
        db.set_state(user_id, "reg:department", data)
        await update.message.reply_text(
            "📚 *Step 4 of 8 — Department*\nEnter your department:\n_(e.g. Computer Science, Mass Communication)_",
            parse_mode="Markdown"
        )

    # ── STEP 4: Department ──
    elif step == "department":
        if len(text) < 2 or len(text) > 80:
            await update.message.reply_text("❌ Department too short/long. Try again:")
            return True
        data['department'] = text
        db.set_state(user_id, "reg:level", data)
        await update.message.reply_text(
            "🎯 *Step 5 of 8 — Level*\nSelect your current level:",
            parse_mode="Markdown",
            reply_markup=levels_keyboard()
        )

    # ── STEP 5: Level ──
    elif step == "level":
        if text not in LEVELS:
            await update.message.reply_text("❌ Please select a valid level from the options.")
            return True
        data['level'] = text
        db.set_state(user_id, "reg:state", data)
        await update.message.reply_text(
            "📍 *Step 6 of 8 — State of Origin*\nSelect your state:",
            parse_mode="Markdown",
            reply_markup=states_keyboard()
        )

    # ── STEP 6: State ──
    elif step == "state":
        if text not in NIGERIAN_STATES:
            await update.message.reply_text("❌ Please select a valid Nigerian state from the keyboard.")
            return True
        data['state'] = text
        db.set_state(user_id, "reg:interests", {**data, 'interests': []})
        await update.message.reply_text(
            "🌟 *Step 7 of 8 — Interests*\nSelect your interests (tap multiple, then tap ✅ Done):",
            parse_mode="Markdown",
            reply_markup=interests_keyboard()
        )

    # ── STEP 7: Interests ──
    elif step == "interests":
        if text == "✅ Done":
            if not data.get('interests'):
                await update.message.reply_text("❌ Please select at least one interest.")
                return True
            db.set_state(user_id, "reg:bio", data)
            await update.message.reply_text(
                "💬 *Step 8 of 8 — Bio*\nWrite a short bio about yourself (max 200 chars).\n\n"
                "_e.g. 'Tech enthusiast, building the next big app. Open to collabs!'_\n\n"
                "Or send /skip to use a default.",
                parse_mode="Markdown",
                reply_markup=cancel_keyboard()
            )
        elif text in INTERESTS:
            current = data.get('interests', [])
            if text in current:
                current.remove(text)
                await update.message.reply_text(f"➖ Removed: {text}\n\nSelected: {', '.join(current) or 'none'}\n\nTap ✅ Done when finished.")
            else:
                if len(current) >= 5:
                    await update.message.reply_text("❌ Max 5 interests. Tap ✅ Done or remove one first.")
                    return True
                current.append(text)
                await update.message.reply_text(f"✅ Added: {text}\n\nSelected: {', '.join(current)}\n\nContinue selecting or tap ✅ Done.")
            data['interests'] = current
            db.set_state(user_id, "reg:interests", data)
        else:
            await update.message.reply_text("Please use the keyboard buttons to select interests.")
        return True

    # ── STEP 8: Bio ──
    elif step == "bio":
        bio = text
        if text == "/skip":
            bio = f"{data['department']} student at {data['school']}"
        elif len(text) > 200:
            await update.message.reply_text("❌ Bio too long (max 200 chars). Try again:")
            return True

        data['bio'] = bio
        # Save the user
        user_data = {
            'id': user_id,
            'username': update.effective_user.username,
            'full_name': data['full_name'],
            'phone': data['phone'],
            'school': data['school'],
            'department': data['department'],
            'level': data['level'],
            'state': data['state'],
            'interests': data['interests'],
            'bio': data['bio'],
            'profile_photo_id': None
        }
        db.create_user(user_data)
        db.clear_state(user_id)

        user_obj = db.get_user(user_id)
        card = format_profile_card(user_obj)

        await update.message.reply_text(
            f"🎉 *Welcome to CampusConnect, {data['full_name']}!*\n\n"
            f"Your profile is live! Here's how it looks:\n\n{card}\n\n"
            f"You're now part of Nigeria's student network. Use the menu below to explore! 🚀",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )
        return True, user_obj  # signal to post to channel

    return True
