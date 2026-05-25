"""
CampusConnect — Registration Flow
Opens a Telegram Mini App (webapp/register.html) to collect:
  full_name, whatsapp_number, school, department, date_of_birth, show_whatsapp
Then falls back to text-based level/state/interests/bio steps.
"""
import json
import os
from datetime import datetime
from telegram import Update, WebAppInfo, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
import database as db
from utils import (
    NIGERIAN_STATES, LEVELS, INTERESTS,
    validate_phone, format_whatsapp, format_profile_card,
    states_keyboard, levels_keyboard, interests_keyboard,
    cancel_keyboard, main_menu_keyboard
)

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-deployment-url.vercel.app/register.html")


# ── Open Mini App ──

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

    db.set_state(user_id, "reg:webapp", {})

    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton(
            "📝 Open Registration Form",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await update.message.reply_text(
        "🎓 *Welcome to CampusConnect!*\n\n"
        "Nigeria's student network — right inside Telegram.\n\n"
        "Tap the button below to fill in your details:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


# ── Receive Mini App data ──

async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Called when the Mini App submits the form via sendData()."""
    user_id = update.effective_user.id

    try:
        raw = update.message.web_app_data.data
        form = json.loads(raw)
    except Exception:
        await update.message.reply_text("❌ Could not read form data. Please try again.")
        return

    name = (form.get("full_name") or "").strip()
    wa_raw = (form.get("whatsapp_number") or "").strip()
    school = (form.get("school") or "").strip().upper()
    department = (form.get("department") or "").strip()
    dob_str = (form.get("date_of_birth") or "").strip()
    show_wa = bool(form.get("show_whatsapp", True))

    errors = []
    if len(name) < 3 or len(name) > 60:
        errors.append("❌ Full name must be 3–60 characters")

    wa_number = format_whatsapp(wa_raw)
    if not wa_number:
        errors.append("❌ Invalid WhatsApp number (use 08012345678 format)")

    if len(school) < 2:
        errors.append("❌ School name too short")
    if len(department) < 2:
        errors.append("❌ Department too short")

    dob = None
    if dob_str:
        try:
            dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
            if dob.year < 1980 or dob > datetime.today().date():
                errors.append("❌ Invalid date of birth")
        except ValueError:
            errors.append("❌ Date of birth format invalid (YYYY-MM-DD)")

    if errors:
        await update.message.reply_text("\n".join(errors) + "\n\nPlease open the form again.")
        return

    # Store mini-app data, continue with level/state/interests/bio steps
    db.set_state(user_id, "reg:level", {
        "full_name": name,
        "whatsapp_number": wa_number,
        "phone": wa_number,   # phone mirrors whatsapp for backward compat
        "school": school,
        "department": department,
        "date_of_birth": dob_str,
        "show_whatsapp": show_wa,
    })

    await update.message.reply_text(
        f"✅ Got it, *{name}*!\n\n🎯 *Select your current level:*",
        parse_mode="Markdown",
        reply_markup=levels_keyboard()
    )


# ── Remaining text steps (level → state → interests → bio) ──

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

    # Legacy text stage1 kept for fallback (no Mini App)
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
        data['whatsapp_number'] = phone
        data['school'] = school.upper()
        data['department'] = department
        data.setdefault('show_whatsapp', True)
        db.set_state(user_id, "reg:level", data)
        await update.message.reply_text(
            "✅ Got it!\n\n🎯 *Select your current level:*",
            parse_mode="Markdown",
            reply_markup=levels_keyboard()
        )

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
            'phone': data.get('phone') or data.get('whatsapp_number'),
            'whatsapp_number': data.get('whatsapp_number'),
            'date_of_birth': data.get('date_of_birth') or None,
            'show_whatsapp': data.get('show_whatsapp', True),
            'school': data['school'],
            'department': data['department'],
            'level': data['level'],
            'state': data['state'],
            'interests': data['interests'],
            'bio': data['bio'],
            'profile_photo_id': None,
        }
        db.create_user(user_data)
        db.clear_state(user_id)

        user_obj = db.get_user(user_id)
        card = format_profile_card(user_obj, is_own_profile=True)

        await update.message.reply_text(
            f"🎉 *Welcome to CampusConnect, {data['full_name']}!*\n\n"
            f"Your profile is live! Here's how it looks:\n\n{card}\n\n"
            f"You're now part of Nigeria's student network. Use the menu below to explore! 🚀",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )
        return True, user_obj

    return True
