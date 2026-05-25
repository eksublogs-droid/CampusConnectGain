"""
CampusConnect — Registration Flow (3 stages)
Stage 1: Name, Phone, School, Department (one message)
Stage 2: Level (keyboard) → State (keyboard)
Stage 3: Interests (keyboard) → Bio (text)
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

TEMPLATE = (
    "Name: \n"
    "Phone: \n"
    "School: \n"
    "Department: "
)


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

    db.set_state(user_id, "reg:stage1", {})
    await update.message.reply_text(
        "🎓 *Welcome to CampusConnect!*\n\n"
        "Nigeria's student network — right inside Telegram.\n\n"
        "Fill in your details and send it back like this:\n\n"
        "```\n"
        "Name: Your Full Name\n"
        "Phone: 08012345678\n"
        "School: EKSU\n"
        "Department: Computer Science"
        "```\n\n"
        "_Copy, fill in your details, and send!_",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )


async def handle_registration_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text == "❌ Cancel":
        db.clear_state(user_id)
        await update.message.reply_text("Registration cancelled.", reply_markup=main_menu_keyboard())
        return True

    state, data = db.get_state(user_id)
    if not state or not state.startswith("reg:"):
        return False

    step = state.split("reg:")[1]

    # ── STAGE 1: Name, Phone, School, Department ──
    if step == "stage1":
        lines = {}
        for line in text.splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                lines[key.strip().lower()] = val.strip()

        name = lines.get("name", "")
        phone_raw = lines.get("phone", "")
        school = lines.get("school", "")
        department = lines.get("department", "")

        errors = []
        if len(name) < 3 or len(name) > 60:
            errors.append("❌ Name must be 3–60 characters")
        phone = validate_phone(phone_raw)
        if not phone:
            errors.append("❌ Invalid phone number (use format: 08012345678)")
        if len(school) < 2 or len(school) > 80:
            errors.append("❌ School name is too short or too long")
        if len(department) < 2 or len(department) > 80:
            errors.append("❌ Department is too short or too long")

        if errors:
            await update.message.reply_text(
                "\n".join(errors) + "\n\nPlease fill and send again:\n\n"
                "```\nName: Your Full Name\nPhone: 08012345678\nSchool: EKSU\nDepartment: Computer Science\n```",
                parse_mode="Markdown"
            )
            return True

        data['full_name'] = name
        data['phone'] = phone
        data['school'] = school.upper()
        data['department'] = department
        db.set_state(user_id, "reg:level", data)
        await update.message.reply_text(
            "✅ Got it!\n\n🎯 *Select your current level:*",
            parse_mode="Markdown",
            reply_markup=levels_keyboard()
        )

    # ── STAGE 2a: Level ──
    elif step == "level":
        if text not in LEVELS:
            await update.message.reply_text("❌ Please select a valid level from the options.")
            return True
        data['level'] = text
        db.set_state(user_id, "reg:state", data)
        await update.message.reply_text(
            "📍 *Select your state of origin:*",
            parse_mode="Markdown",
            reply_markup=states_keyboard()
        )

    # ── STAGE 2b: State ──
    elif step == "state":
        if text not in NIGERIAN_STATES:
            await update.message.reply_text("❌ Please select a valid Nigerian state from the keyboard.")
            return True
        data['state'] = text
        db.set_state(user_id, "reg:interests", {**data, 'interests': []})
        await update.message.reply_text(
            "🌟 *Select your interests* (tap multiple, then tap ✅ Done):",
            parse_mode="Markdown",
            reply_markup=interests_keyboard()
        )

    # ── STAGE 3a: Interests ──
    elif step == "interests":
        if text == "✅ Done":
            if not data.get('interests'):
                await update.message.reply_text("❌ Please select at least one interest.")
                return True
            db.set_state(user_id, "reg:bio", data)
            await update.message.reply_text(
                "💬 *Almost done! Write a short bio* (max 200 chars).\n\n"
                "_e.g. 'Tech enthusiast, building the next big app. Open to collabs!'_\n\n"
                "Or send /skip to use a default.",
                parse_mode="Markdown",
                reply_markup=cancel_keyboard()
            )
        elif text in INTERESTS:
            current = data.get('interests', [])
            if text in current:
                current.remove(text)
                await update.message.reply_text(
                    f"➖ Removed: {text}\n\nSelected: {', '.join(current) or 'none'}\n\nTap ✅ Done when finished."
                )
            else:
                if len(current) >= 5:
                    await update.message.reply_text("❌ Max 5 interests. Tap ✅ Done or remove one first.")
                    return True
                current.append(text)
                await update.message.reply_text(
                    f"✅ Added: {text}\n\nSelected: {', '.join(current)}\n\nContinue selecting or tap ✅ Done."
                )
            data['interests'] = current
            db.set_state(user_id, "reg:interests", data)
        else:
            await update.message.reply_text("Please use the keyboard buttons to select interests.")
        return True

    # ── STAGE 3b: Bio ──
    elif step == "bio":
        bio = text
        if text == "/skip":
            bio = f"{data['department']} student at {data['school']}"
        elif len(text) > 200:
            await update.message.reply_text("❌ Bio too long (max 200 chars). Try again:")
            return True

        data['bio'] = bio
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
        return True, user_obj

    return True
