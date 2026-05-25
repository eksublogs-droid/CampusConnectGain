"""
CampusConnect — Contact Drop System
/contactdrop, /drophistory, /dropstats
"""
import os
import io
from telegram import Update
from telegram.ext import ContextTypes
import database as db
from utils import (
    generate_vcf, generate_reference, create_paystack_payment,
    drop_tier_keyboard, main_menu_keyboard
)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


async def cmd_contactdrop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.get_user(user_id):
        await update.message.reply_text("❌ Register first with /start")
        return

    await update.message.reply_text(
        "📬 *Contact Drop*\n\n"
        "Receive VCF contact files directly in your DM!\n\n"
        "🆓 *Free Drop*\n"
        "New registrations from the last 3 days.\n"
        "Delivered every 3 days automatically.\n\n"
        "⭐ *Premium Drop — ₦500/drop*\n"
        "Full database VCF + new additions every 3 days.\n"
        "Filter by school/state available.\n\n"
        "Choose your tier:",
        parse_mode="Markdown",
        reply_markup=drop_tier_keyboard()
    )


async def cmd_drophistory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.get_user(user_id):
        await update.message.reply_text("❌ Register first with /start")
        return

    history = db.get_drop_history(user_id)
    if not history:
        await update.message.reply_text(
            "📬 No drop history yet.\n\nSubscribe to /contactdrop to start receiving contact batches!"
        )
        return

    msg = "📬 *Your Drop History*\n\n"
    for d in history:
        tier_label = "⭐ Premium" if d['tier'] == 'premium' else "🆓 Free"
        msg += (
            f"{tier_label} · {d['contacts_count']} contacts\n"
            f"📅 {str(d['sent_at'])[:16]}\n\n"
        )

    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_dropstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin only"""
    user_id = update.effective_user.id
    admin_ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
    if user_id not in admin_ids:
        return

    free_subs = len(db.get_drop_subscribers('free'))
    premium_subs = len(db.get_drop_subscribers('premium'))

    await update.message.reply_text(
        f"📊 *Drop Stats*\n\n"
        f"🆓 Free subscribers: {free_subs}\n"
        f"⭐ Premium subscribers: {premium_subs}\n"
        f"📬 Total: {free_subs + premium_subs}",
        parse_mode="Markdown"
    )


async def handle_drop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "drop:free":
        db.subscribe_drop(user_id, 'free')
        # Send current free drop immediately
        recent_users = db.get_recent_users(days=3)
        if recent_users:
            vcf_data = generate_vcf(recent_users)
            vcf_file = io.BytesIO(vcf_data)
            vcf_file.name = "campusconnect_new_students.vcf"
            msg = await context.bot.send_document(
                user_id,
                vcf_file,
                caption=(
                    f"📬 *Free Contact Drop*\n\n"
                    f"Here are {len(recent_users)} students who joined in the last 3 days!\n\n"
                    f"Save to your contacts and grow your network 🚀\n"
                    f"Next drop in 3 days."
                ),
                parse_mode="Markdown"
            )
            db.log_drop(user_id, 'free', str(msg.document.file_id), len(recent_users))
            await query.message.reply_text("✅ You're subscribed to free drops! Check your DMs for your first batch.", reply_markup=main_menu_keyboard())
        else:
            await query.message.reply_text("✅ Subscribed! No new students in the last 3 days, but you'll get the next drop automatically.")

    elif data == "drop:premium":
        user = db.get_user(user_id)
        reference = generate_reference("DROP", user_id)
        fake_email = f"user{user_id}@campusconnect.ng"
        try:
            pay_url, ref = create_paystack_payment(
                fake_email, 500, reference,
                metadata={'type': 'drop', 'tier': 'premium', 'user_id': user_id}
            )
            await query.message.reply_text(
                "⭐ *Premium Contact Drop — ₦500*\n\n"
                "You'll receive the full student database as VCF!\n\n"
                "Pay below to get your first drop immediately:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Pay ₦500", url=pay_url)],
                    [InlineKeyboardButton("✅ I've Paid — Verify", callback_data=f"drop:verify:{ref}")]
                ])
            )
        except Exception as e:
            await query.message.reply_text(f"❌ Payment setup failed. Try again.")

    elif data.startswith("drop:verify:"):
        reference = data.split("drop:verify:")[1]
        from utils import verify_paystack_payment
        paid, info = verify_paystack_payment(reference)
        if paid:
            db.subscribe_drop(user_id, 'premium')
            db.log_revenue(user_id, 'drop_premium', 500, reference)
            # Send full VCF
            all_users = db.get_all_users()
            if all_users:
                vcf_data = generate_vcf(all_users)
                vcf_file = io.BytesIO(vcf_data)
                vcf_file.name = "campusconnect_full_database.vcf"
                msg = await context.bot.send_document(
                    user_id,
                    vcf_file,
                    caption=(
                        f"⭐ *Premium Contact Drop*\n\n"
                        f"Full database: {len(all_users)} contacts!\n\n"
                        f"Save all to your phone contacts and grow your network!\n"
                        f"Next drop in 3 days — automatically sent to your DM 🚀"
                    ),
                    parse_mode="Markdown"
                )
                db.log_drop(user_id, 'premium', str(msg.document.file_id), len(all_users))
            await query.message.reply_text("✅ Premium drop activated! Check DMs for your VCF.", reply_markup=main_menu_keyboard())
        else:
            await query.message.reply_text(
                "❌ Payment not confirmed yet.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Try Again", callback_data=f"drop:verify:{reference}")]
                ])
            )


async def run_scheduled_drop(bot):
    """Called by scheduler every 3 days"""
    print("Running scheduled contact drop...")

    # Free drop — new students
    free_subs = db.get_drop_subscribers('free')
    recent_users = db.get_recent_users(days=3)

    if recent_users and free_subs:
        vcf_data = generate_vcf(recent_users)
        for sub in free_subs:
            try:
                vcf_file = io.BytesIO(vcf_data)
                vcf_file.name = "campusconnect_new_students.vcf"
                msg = await bot.send_document(
                    sub['user_id'],
                    vcf_file,
                    caption=(
                        f"📬 *Free Contact Drop* 🆕\n\n"
                        f"{len(recent_users)} new students this cycle!\n"
                        f"Import to your contacts to stay connected."
                    ),
                    parse_mode="Markdown"
                )
                db.log_drop(sub['user_id'], 'free', str(msg.document.file_id), len(recent_users))
            except Exception as e:
                print(f"Drop failed for {sub['user_id']}: {e}")

    # Premium drop — full DB
    premium_subs = db.get_drop_subscribers('premium')
    all_users = db.get_all_users()

    if all_users and premium_subs:
        vcf_data = generate_vcf(all_users)
        for sub in premium_subs:
            try:
                vcf_file = io.BytesIO(vcf_data)
                vcf_file.name = "campusconnect_full_database.vcf"
                msg = await bot.send_document(
                    sub['user_id'],
                    vcf_file,
                    caption=(
                        f"⭐ *Premium Contact Drop* 🔄\n\n"
                        f"Full database: {len(all_users)} contacts!\n"
                        f"Includes all new additions."
                    ),
                    parse_mode="Markdown"
                )
                db.log_drop(sub['user_id'], 'premium', str(msg.document.file_id), len(all_users))
            except Exception as e:
                print(f"Premium drop failed for {sub['user_id']}: {e}")

    print(f"Drop complete: {len(free_subs)} free, {len(premium_subs)} premium")
