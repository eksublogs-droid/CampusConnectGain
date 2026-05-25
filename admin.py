"""
CampusConnect — Admin Panel
/stats, /broadcast, /lookup, /approve, /remove, /blacklist,
/revenue, /export, /adqueue, /orders, /fulfillorder, /rundrop
"""
import os
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import database as db
from utils import (
    format_profile_card, generate_vcf, generate_excel,
    sync_to_google_sheets, cancel_keyboard, AD_TIERS
)

def get_admin_ids():
    return [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]


def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in get_admin_ids():
            await update.effective_message.reply_text("❌ Admin only command.")
            return
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper


@admin_only
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = db.get_platform_stats()
    by_school = db.get_users_by_school()
    by_state = db.get_users_by_state()

    school_breakdown = "\n".join([f"  • {r['school']}: {r['c']}" for r in by_school[:5]])
    state_breakdown = "\n".join([f"  • {r['state']}: {r['c']}" for r in by_state[:5]])

    msg = (
        f"📊 *CampusConnect Stats*\n\n"
        f"👥 Total Users: *{stats['total_users']:,}*\n"
        f"🆕 New This Week: *{stats['new_this_week']:,}*\n"
        f"📦 Total Orders: *{stats['total_orders']:,}*\n"
        f"💰 Total Revenue: *₦{stats['total_revenue']:,}*\n"
        f"📡 Active Ads: *{stats['active_ads']:,}*\n"
        f"📬 Drop Subscribers: *{stats['drop_subscribers']:,}*\n\n"
        f"🏫 *Top Schools:*\n{school_breakdown}\n\n"
        f"📍 *Top States:*\n{state_breakdown}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


@admin_only
async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        db.set_state(update.effective_user.id, "admin:broadcast", {})
        await update.message.reply_text("📣 Enter the message to broadcast to ALL users:", reply_markup=cancel_keyboard())
        return

    message = " ".join(args)
    await _do_broadcast(update, context, message)


@admin_only
async def cmd_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /lookup [name/username/phone]")
        return

    query = " ".join(args)
    users = db.lookup_user(query)
    if not users:
        await update.message.reply_text(f"😕 No user found matching '{query}'")
        return

    for u in users:
        card = format_profile_card(u)
        status = "🚫 Blacklisted" if u['is_blacklisted'] else ("✅ Active" if u['is_active'] else "⚠️ Inactive")
        await update.message.reply_text(
            f"{card}\n\n🆔 ID: `{u['id']}`\nStatus: {status}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚫 Blacklist", callback_data=f"admin:blacklist:{u['id']}"),
                 InlineKeyboardButton("🗑️ Remove", callback_data=f"admin:remove:{u['id']}")]
            ])
        )


@admin_only
async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /approve [ad_id]")
        return
    ad_id = int(args[0])
    ad = db.approve_ad(ad_id)
    if ad:
        user = db.get_user(ad['user_id'])
        tier = ad['tier']
        duration = AD_TIERS.get(tier, {}).get('duration_hours', 24)

        from handlers.ads import _publish_ad
        msg_id = await _publish_ad(ad, user, context.bot, duration)
        if msg_id:
            await update.message.reply_text(f"✅ Ad #{ad_id} approved and published to channel!")
            try:
                await context.bot.send_message(
                    ad['user_id'],
                    f"🎉 *Your Premium Ad is LIVE!*\n\nYour ad has been reviewed and published to the CampusConnect channel!\n\nCheck /myadstatus for details.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        else:
            await update.message.reply_text(f"✅ Ad approved but channel post failed. Check CHANNEL_ID config.")
    else:
        await update.message.reply_text("❌ Ad not found.")


@admin_only
async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /remove [user_id]")
        return
    user_id = int(args[0])
    db.update_user_field(user_id, 'is_active', False)
    await update.message.reply_text(f"✅ User {user_id} deactivated.")


@admin_only
async def cmd_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /blacklist [user_id]")
        return
    user_id = int(args[0])
    db.blacklist_user(user_id)
    await update.message.reply_text(f"🚫 User {user_id} blacklisted. They cannot re-register.")
    try:
        await context.bot.send_message(user_id, "❌ Your CampusConnect account has been suspended. Contact support if you believe this is an error.")
    except Exception:
        pass


@admin_only
async def cmd_revenue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.get_revenue_stats()
    stats = db.get_platform_stats()

    msg = f"💰 *Revenue Dashboard*\n\n"
    msg += f"📊 *All-Time Total: ₦{stats['total_revenue']:,}*\n\n"
    msg += "*By Source:*\n"

    source_labels = {
        'ad_basic': '🔹 Basic Ads',
        'ad_standard': '🔶 Standard Ads',
        'ad_premium': '💎 Premium Ads',
        'store': '🛒 Store Sales',
        'drop_premium': '📬 Premium Drops',
    }
    totals = {}
    for r in rows:
        label = source_labels.get(r['source'], r['source'])
        day_total = r.get('today') or 0
        week_total = r.get('week') or 0
        month_total = r.get('month') or 0
        all_total = r.get('total') or 0
        msg += f"  {label}: ₦{all_total:,} ({r['tx_count']} txns)\n"

    await update.message.reply_text(msg, parse_mode="Markdown")


@admin_only
async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    export_type = args[0] if args else "vcf"

    # Parse filters
    school = dept = level = state = None
    for arg in args[1:]:
        if arg.upper() in ['100L','200L','300L','400L','500L','600L']:
            level = arg
        elif len(arg) <= 5 and arg.isupper():
            school = arg
        elif arg.istitle():
            state = arg
        else:
            dept = arg

    users = db.search_users(school=school, dept=dept, state=state, limit=10000)

    if export_type == "vcf":
        vcf_data = generate_vcf(users)
        vcf_file = io.BytesIO(vcf_data)
        filter_str = f"_{school or 'all'}" + (f"_{dept}" if dept else "") + (f"_{level}" if level else "")
        vcf_file.name = f"campusconnect{filter_str}.vcf"
        await update.message.reply_document(
            vcf_file,
            caption=f"📇 VCF Export — {len(users)} contacts\n{school or 'All schools'}"
        )

    elif export_type == "excel":
        xlsx_data = generate_excel(users)
        xlsx_file = io.BytesIO(xlsx_data)
        xlsx_file.name = "campusconnect_students.xlsx"
        await update.message.reply_document(
            xlsx_file,
            caption=f"📊 Excel Export — {len(users)} students"
        )
        # Sync to Google Sheets
        await update.message.reply_text("🔄 Syncing to Google Sheets...")
        success = sync_to_google_sheets(users)
        if success:
            await update.message.reply_text("✅ Google Sheets synced!")
        else:
            await update.message.reply_text("⚠️ Sheets sync failed. Check GOOGLE credentials in .env")
    else:
        await update.message.reply_text("Usage: /export vcf [filters] or /export excel")


@admin_only
async def cmd_adqueue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = db.get_pending_ads()
    if not pending:
        await update.message.reply_text("✅ No premium ads pending review.")
        return

    await update.message.reply_text(f"📢 *Ad Queue — {len(pending)} pending*\n", parse_mode="Markdown")
    for ad in pending:
        tier_info = AD_TIERS.get(ad['tier'], {})
        msg = (
            f"💎 *Premium Ad #{ad['id']}*\n\n"
            f"By: {ad['full_name']} (@{ad.get('username','N/A')})\n"
            f"Copy:\n{ad['ad_copy']}\n\n"
            f"{'📷 Has image' if ad.get('image_file_id') else '📝 Text only'}"
        )
        if ad.get('image_file_id'):
            await update.message.reply_photo(
                ad['image_file_id'],
                caption=msg,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Approve", callback_data=f"admin:approveAd:{ad['id']}"),
                     InlineKeyboardButton("❌ Reject", callback_data=f"admin:rejectAd:{ad['id']}")]
                ])
            )
        else:
            await update.message.reply_text(
                msg, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Approve", callback_data=f"admin:approveAd:{ad['id']}"),
                     InlineKeyboardButton("❌ Reject", callback_data=f"admin:rejectAd:{ad['id']}")]
                ])
            )


@admin_only
async def cmd_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    orders = db.get_pending_orders()
    if not orders:
        await update.message.reply_text("✅ No orders pending delivery.")
        return

    msg = f"📦 *Pending Deliveries — {len(orders)} orders*\n\n"
    for o in orders:
        msg += f"• Order #{o['id']} — {o['item_name']}\n  By: {o['full_name']} (ID: {o['user_id']})\n  ₦{o['amount']:,}\n\n"

    msg += "Use /fulfillorder [id] to mark as delivered."
    await update.message.reply_text(msg, parse_mode="Markdown")


@admin_only
async def cmd_fulfillorder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /fulfillorder [order_id]")
        return
    order_id = int(args[0])
    db.mark_delivered(order_id)
    await update.message.reply_text(f"✅ Order #{order_id} marked as delivered.")


@admin_only
async def cmd_rundrop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Running manual contact drop...")
    from handlers.drops import run_scheduled_drop
    await run_scheduled_drop(context.bot)
    await update.message.reply_text("✅ Manual drop complete!")


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in get_admin_ids():
        await query.answer("Admin only!", show_alert=True)
        return

    data = query.data

    if data.startswith("admin:blacklist:"):
        target_id = int(data.split(":")[2])
        db.blacklist_user(target_id)
        await query.message.reply_text(f"🚫 User {target_id} blacklisted.")

    elif data.startswith("admin:remove:"):
        target_id = int(data.split(":")[2])
        db.update_user_field(target_id, 'is_active', False)
        await query.message.reply_text(f"✅ User {target_id} removed.")

    elif data.startswith("admin:approveAd:"):
        ad_id = int(data.split(":")[2])
        ad = db.approve_ad(ad_id)
        if ad:
            user = db.get_user(ad['user_id'])
            duration = AD_TIERS.get(ad['tier'], {}).get('duration_hours', 168)
            from handlers.ads import _publish_ad
            msg_id = await _publish_ad(ad, user, context.bot, duration)
            await query.message.reply_text(f"✅ Ad #{ad_id} published!" if msg_id else "✅ Approved but channel post failed.")
            try:
                await context.bot.send_message(
                    ad['user_id'],
                    "🎉 *Your Premium Ad is now LIVE on CampusConnect channel!*\n\nCheck /myadstatus",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    elif data.startswith("admin:rejectAd:"):
        ad_id = int(data.split(":")[2])
        db.reject_ad(ad_id, "Does not meet community guidelines")
        await query.message.reply_text(f"❌ Ad #{ad_id} rejected.")


async def handle_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in get_admin_ids():
        return False

    state, data = db.get_state(user_id)
    if state == "admin:broadcast":
        text = update.message.text.strip()
        if text == "❌ Cancel":
            db.clear_state(user_id)
            return True
        await _do_broadcast(update, context, text)
        db.clear_state(user_id)
        return True
    return False


async def _do_broadcast(update, context, message):
    users = db.get_all_users()
    count = 0
    failed = 0
    await update.effective_message.reply_text(f"📣 Broadcasting to {len(users)} users...")

    for u in users:
        try:
            await context.bot.send_message(
                u['id'],
                f"📣 *CampusConnect Announcement*\n\n{message}",
                parse_mode="Markdown"
            )
            count += 1
        except Exception:
            failed += 1

    # Log broadcast
    with db.db() as cur:
        cur.execute("INSERT INTO broadcasts (admin_id, message, sent_count) VALUES (%s,%s,%s)",
                    (update.effective_user.id, message, count))

    await update.effective_message.reply_text(
        f"✅ Broadcast sent!\n✅ Delivered: {count}\n❌ Failed: {failed}"
    )


async def notify_admin_new_ad(bot, ad):
    admin_ids = get_admin_ids()
    for admin_id in admin_ids:
        try:
            await bot.send_message(
                admin_id,
                f"💎 *New Premium Ad — Review Required*\n\n"
                f"Ad ID: #{ad['id']}\n"
                f"Use /adqueue to review and approve.",
                parse_mode="Markdown"
            )
        except Exception:
            pass
