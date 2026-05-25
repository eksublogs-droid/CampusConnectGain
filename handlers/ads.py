"""
CampusConnect — Ads System
/runad, /myadstatus
"""
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import database as db
from utils import (
    AD_TIERS, generate_reference, create_paystack_payment,
    format_ad_channel_post, cancel_keyboard, main_menu_keyboard,
    ad_tier_keyboard, check_rate_limit
)

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")


async def cmd_runad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Register first with /start")
        return

    if not check_rate_limit(user_id, "runad", 3):
        await update.message.reply_text("⏳ You're doing that too fast. Please wait.")
        return

    db.set_state(user_id, "ad:tier", {})
    await update.message.reply_text(
        "📢 *Run an Ad on CampusConnect*\n\n"
        "Reach students across Nigerian universities!\n\n"
        "🔹 *Basic* — ₦500\n"
        "  Text post · 24hrs pinned · ~500–2k impressions\n\n"
        "🔶 *Standard* — ₦1,500\n"
        "  Text + image · 48hrs · Broadcast to all users · ~2k–8k impressions\n\n"
        "💎 *Premium* — ₦4,000\n"
        "  Text + image/video · 7 days · Targeted DMs · Analytics\n\n"
        "Select your tier:",
        parse_mode="Markdown",
        reply_markup=ad_tier_keyboard()
    )


async def cmd_myadstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Register first with /start")
        return

    ads = db.get_user_ads(user_id)
    if not ads:
        await update.message.reply_text("📢 You haven't run any ads yet.\nUse /runad to get started!")
        return

    msg = "📢 *Your Ads*\n\n"
    for ad in ads:
        tier_info = AD_TIERS.get(ad['tier'], {})
        status_emoji = {
            'pending': '⏳', 'paid': '✅', 'active': '📡',
            'expired': '⌛', 'rejected': '❌'
        }.get(ad['status'], '❓')

        msg += (
            f"{status_emoji} *{tier_info.get('label', ad['tier'])}* — ₦{ad['amount']:,}\n"
            f"Status: {ad['status'].upper()}\n"
            f"Copy: {ad['ad_copy'][:60]}{'...' if len(ad['ad_copy']) > 60 else ''}\n"
        )
        if ad['expires_at']:
            msg += f"Expires: {str(ad['expires_at'])[:16]}\n"
        msg += "\n"

    await update.message.reply_text(msg, parse_mode="Markdown")


async def handle_ad_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("adtier:"):
        tier = data.split(":")[1]
        if tier not in AD_TIERS:
            await query.answer("Invalid tier", show_alert=True)
            return
        tier_info = AD_TIERS[tier]
        db.set_state(user_id, "ad:copy", {'tier': tier})
        await query.message.reply_text(
            f"✍️ *{tier_info['label']} Ad*\n\n"
            f"Write your ad message (max 400 chars):\n\n"
            f"_Include what you're offering, your price, and how to order._",
            parse_mode="Markdown",
            reply_markup=cancel_keyboard()
        )

    elif data == "ad:add_image":
        state, ad_data = db.get_state(user_id)
        ad_data['waiting_image'] = True
        db.set_state(user_id, "ad:image", ad_data)
        await query.message.reply_text("📷 Send your ad image now:", reply_markup=cancel_keyboard())

    elif data == "ad:skip_image":
        state, ad_data = db.get_state(user_id)
        await _proceed_to_preview(query.message, user_id, ad_data, context)

    elif data == "ad:confirm_pay":
        state, ad_data = db.get_state(user_id)
        user = db.get_user(user_id)
        tier = ad_data.get('tier')
        tier_info = AD_TIERS[tier]
        reference = generate_reference("AD", user_id)

        fake_email = f"user{user_id}@campusconnect.ng"
        try:
            pay_url, ref = create_paystack_payment(
                fake_email, tier_info['price'], reference,
                metadata={'type': 'ad', 'user_id': user_id, 'tier': tier}
            )
            ad_id = db.create_ad(
                user_id, tier, ad_data['copy'], tier_info['price'], ref,
                image_file_id=ad_data.get('image_file_id')
            )
            ad_data['ad_id'] = ad_id
            ad_data['reference'] = ref
            db.set_state(user_id, "ad:awaiting_payment", ad_data)

            await query.message.reply_text(
                f"💳 *Pay for Your Ad*\n\n"
                f"Amount: ₦{tier_info['price']:,}\n"
                f"Tier: {tier_info['label']}\n\n"
                f"Click the button below to pay securely via Paystack:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"💳 Pay ₦{tier_info['price']:,}", url=pay_url)],
                    [InlineKeyboardButton("✅ I've Paid — Verify", callback_data=f"ad:verify:{ref}")]
                ])
            )
        except Exception as e:
            await query.message.reply_text(f"❌ Payment setup failed: {str(e)}")

    elif data.startswith("ad:verify:"):
        reference = data.split("ad:verify:")[1]
        from utils import verify_paystack_payment
        paid, info = verify_paystack_payment(reference)
        if paid:
            state, ad_data = db.get_state(user_id)
            # Update ad status
            tier = ad_data.get('tier', 'basic')
            ad = db.get_ad_by_reference(reference)
            if ad:
                user = db.get_user(user_id)
                db.log_revenue(user_id, f"ad_{tier}", AD_TIERS[tier]['price'], reference)

                if tier == 'premium':
                    # Queue for admin review
                    from admin import notify_admin_new_ad
                    await notify_admin_new_ad(context.bot, ad)
                    with db.db() as cur:
                        cur.execute("UPDATE ads SET status='paid' WHERE paystack_reference=%s", (reference,))
                    await query.message.reply_text(
                        "✅ *Payment confirmed!*\n\n"
                        "Your Premium ad is in review. The admin will publish it shortly.\n"
                        "Check status with /myadstatus",
                        parse_mode="Markdown",
                        reply_markup=main_menu_keyboard()
                    )
                else:
                    # Auto-publish
                    duration = AD_TIERS[tier]['duration_hours']
                    with db.db() as cur:
                        cur.execute("UPDATE ads SET status='paid' WHERE paystack_reference=%s", (reference,))
                    await _publish_ad(ad, user, context.bot, duration)
                    await query.message.reply_text(
                        "🎉 *Ad is LIVE!*\n\nYour ad has been published to the CampusConnect channel!\n\n"
                        "Track it with /myadstatus",
                        parse_mode="Markdown",
                        reply_markup=main_menu_keyboard()
                    )
                    # Broadcast for standard tier
                    if tier == 'standard':
                        await _broadcast_ad(ad, user, context.bot)
                db.clear_state(user_id)
            else:
                await query.message.reply_text("❌ Ad not found. Contact support.")
        else:
            await query.message.reply_text(
                "❌ Payment not verified yet.\n\nComplete payment on Paystack, then tap verify again.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Try Again", callback_data=f"ad:verify:{reference}")]
                ])
            )

    elif data.startswith("ad:edit:"):
        reference = data.split("ad:edit:")[1]
        state, ad_data = db.get_state(user_id)
        db.set_state(user_id, "ad:copy", {'tier': ad_data.get('tier', 'basic')})
        await query.message.reply_text("✏️ Rewrite your ad copy:", reply_markup=cancel_keyboard())


async def handle_ad_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state, ad_data = db.get_state(user_id)
    if not state or not state.startswith("ad:"):
        return False

    text = update.message.text
    if text == "❌ Cancel":
        db.clear_state(user_id)
        await update.message.reply_text("Ad cancelled.", reply_markup=main_menu_keyboard())
        return True

    step = state.split("ad:")[1]

    if step == "copy":
        if len(text) > 400:
            await update.message.reply_text("❌ Too long. Keep it under 400 characters.")
            return True
        ad_data['copy'] = text
        tier = ad_data.get('tier', 'basic')

        if tier in ('standard', 'premium'):
            db.set_state(user_id, "ad:image_prompt", ad_data)
            await update.message.reply_text(
                "🖼️ Add an image to your ad? (recommended for better results)",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📷 Add Image", callback_data="ad:add_image"),
                     InlineKeyboardButton("⏭ Skip", callback_data="ad:skip_image")]
                ])
            )
        else:
            await _proceed_to_preview(update.message, user_id, ad_data, context)
        return True

    if step == "image":
        if update.message.photo:
            photo = update.message.photo[-1]
            ad_data['image_file_id'] = photo.file_id
            db.set_state(user_id, "ad:image_prompt", ad_data)
            await _proceed_to_preview(update.message, user_id, ad_data, context)
        else:
            await update.message.reply_text("Please send an image file.")
        return True

    return False


async def _proceed_to_preview(message, user_id, ad_data, context):
    tier = ad_data.get('tier', 'basic')
    tier_info = AD_TIERS[tier]
    user = db.get_user(user_id)

    preview = (
        f"📋 *Ad Preview*\n\n"
        f"📢 *SPONSORED* {tier_info['label']}\n\n"
        f"{ad_data['copy']}\n\n"
        f"👤 {user['full_name']} · {user['school']}\n"
        f"📱 {user['phone']}\n"
        f"━━━━━━━━━━━━━━\n"
        f"Tier: {tier_info['label']} · ₦{tier_info['price']:,}\n"
        f"Duration: {tier_info['duration_hours']}hrs\n"
        f"{'📷 With image' if ad_data.get('image_file_id') else '📝 Text only'}"
    )

    db.set_state(user_id, "ad:preview", ad_data)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💳 Pay ₦{tier_info['price']:,}", callback_data="ad:confirm_pay"),
         InlineKeyboardButton("✏️ Edit", callback_data="ad:edit:copy")]
    ])

    if ad_data.get('image_file_id'):
        await context.bot.send_photo(
            user_id,
            ad_data['image_file_id'],
            caption=preview,
            parse_mode="Markdown",
            reply_markup=kb
        )
    else:
        await message.reply_text(preview, parse_mode="Markdown", reply_markup=kb)


async def _publish_ad(ad, user, bot, duration_hours):
    channel_id = os.getenv("CHANNEL_ID")
    if not channel_id:
        return None

    text = format_ad_channel_post(ad, user)
    try:
        if ad.get('image_file_id'):
            msg = await bot.send_photo(channel_id, ad['image_file_id'], caption=text, parse_mode="Markdown")
        else:
            msg = await bot.send_message(channel_id, text, parse_mode="Markdown")

        db.activate_ad(ad['paystack_reference'], msg.message_id, duration_hours)
        return msg.message_id
    except Exception as e:
        print(f"Failed to publish ad: {e}")
        return None


async def _broadcast_ad(ad, user, bot):
    users = db.get_all_users()
    text = (
        f"📢 *Sponsored Message*\n\n"
        f"{ad['ad_copy']}\n\n"
        f"📱 {user['phone']}"
    )
    count = 0
    for u in users:
        try:
            await bot.send_message(u['id'], text, parse_mode="Markdown")
            count += 1
        except Exception:
            pass
    return count
