"""
CampusConnect — Profile Management
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import database as db
from utils import (
    format_profile_card, NIGERIAN_STATES, LEVELS, INTERESTS,
    validate_phone, states_keyboard, levels_keyboard,
    interests_keyboard, cancel_keyboard, main_menu_keyboard
)

EDITABLE_FIELDS = {
    "1": ("full_name", "👤 Full Name"),
    "2": ("phone", "📱 Phone Number"),
    "3": ("school", "🏫 School"),
    "4": ("department", "📚 Department"),
    "5": ("level", "🎯 Level"),
    "6": ("state", "📍 State"),
    "7": ("interests", "🌟 Interests"),
    "8": ("bio", "💬 Bio"),
}


async def cmd_myprofile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("❌ You're not registered yet. Send /start to join!")
        return

    card = format_profile_card(user)
    stats_msg = ""
    
    await update.message.reply_text(
        f"📋 *Your Profile*\n\n{card}\n\n"
        f"Use /edit to update any field.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Edit Profile", callback_data="profile:edit")]
        ])
    )


async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Register first with /start")
        return

    field_list = "\n".join([f"{k}. {v[1]}" for k, v in EDITABLE_FIELDS.items()])
    db.set_state(user_id, "edit:choose_field", {})
    await update.message.reply_text(
        f"✏️ *Edit Profile*\n\nWhich field would you like to update?\n\n{field_list}\n\nSend the number:",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )


async def handle_edit_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text == "❌ Cancel":
        db.clear_state(user_id)
        await update.message.reply_text("✅ Edit cancelled.", reply_markup=main_menu_keyboard())
        return True

    state, data = db.get_state(user_id)
    if not state or not state.startswith("edit:"):
        return False

    step = state.split("edit:")[1]

    if step == "choose_field":
        if text not in EDITABLE_FIELDS:
            await update.message.reply_text("❌ Invalid choice. Send a number 1–8:")
            return True
        field_key, field_label = EDITABLE_FIELDS[text]
        db.set_state(user_id, f"edit:value:{field_key}", {})

        if field_key == "level":
            await update.message.reply_text(f"Select new {field_label}:", reply_markup=levels_keyboard())
        elif field_key == "state":
            await update.message.reply_text(f"Select new {field_label}:", reply_markup=states_keyboard())
        elif field_key == "interests":
            user = db.get_user(user_id)
            current = user.get('interests') or []
            db.set_state(user_id, "edit:value:interests", {'interests': current})
            await update.message.reply_text(
                f"🌟 *Edit Interests*\nCurrent: {', '.join(current) or 'none'}\n\nTap to add/remove, then ✅ Done:",
                parse_mode="Markdown",
                reply_markup=interests_keyboard()
            )
        else:
            await update.message.reply_text(f"Enter new {field_label}:", reply_markup=cancel_keyboard())
        return True

    elif step.startswith("value:"):
        field_key = step.split("value:")[1]
        return await _save_edit(update, user_id, field_key, text, data)

    return True


async def _save_edit(update, user_id, field_key, text, data):
    # Validate
    if field_key == "full_name":
        if len(text) < 3 or len(text) > 60:
            await update.message.reply_text("❌ Name must be 3–60 chars. Try again:")
            return True
        value = text

    elif field_key == "phone":
        value = validate_phone(text)
        if not value:
            await update.message.reply_text("❌ Invalid phone. Use 08012345678 format:")
            return True

    elif field_key == "school":
        if len(text) < 2 or len(text) > 80:
            await update.message.reply_text("❌ Invalid school name. Try again:")
            return True
        value = text.upper()

    elif field_key == "department":
        if len(text) < 2 or len(text) > 80:
            await update.message.reply_text("❌ Invalid department. Try again:")
            return True
        value = text

    elif field_key == "level":
        if text not in LEVELS:
            await update.message.reply_text("❌ Select a valid level from the keyboard.")
            return True
        value = text

    elif field_key == "state":
        if text not in NIGERIAN_STATES:
            await update.message.reply_text("❌ Select a valid state from the keyboard.")
            return True
        value = text

    elif field_key == "interests":
        if text == "✅ Done":
            value = data.get('interests', [])
            if not value:
                await update.message.reply_text("❌ Select at least one interest.")
                return True
        elif text in INTERESTS:
            current = data.get('interests', [])
            if text in current:
                current.remove(text)
            else:
                if len(current) >= 5:
                    await update.message.reply_text("❌ Max 5 interests.")
                    return True
                current.append(text)
            data['interests'] = current
            db.set_state(user_id, "edit:value:interests", data)
            await update.message.reply_text(
                f"Selected: {', '.join(current) or 'none'}\n\nContinue or ✅ Done"
            )
            return True
        else:
            await update.message.reply_text("Use the keyboard buttons.")
            return True
        field_key = "interests"

    elif field_key == "bio":
        if text == "/skip":
            user = db.get_user(user_id)
            text = f"{user['department']} student at {user['school']}"
        if len(text) > 200:
            await update.message.reply_text("❌ Bio too long (max 200 chars).")
            return True
        value = text

    else:
        value = text

    db.update_user_field(user_id, field_key, value)
    db.clear_state(user_id)
    await update.message.reply_text(
        f"✅ *{field_key.replace('_', ' ').title()} updated!*",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )
    return True
