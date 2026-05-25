"""
CampusConnect — Marketplace
/store, /customorder, /myorders
"""
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import database as db
from utils import (
    generate_reference, create_virtual_account, format_payment_message,
    store_category_keyboard, cancel_keyboard, main_menu_keyboard
)

ITEM_TYPE_LABELS = {
    'contact_pack': '📇 Contact Pack',
    'group_link': '🔗 Group Links',
    'tool': '🛠️ Tool',
    'custom': '🎛️ Custom Order',
}


async def cmd_store(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.get_user(user_id):
        await update.message.reply_text("❌ Register first with /start")
        return

    await update.message.reply_text(
        "🛒 *CampusConnect Store*\n\n"
        "Buy contact packs, group links, tools, and more — all delivered inside Telegram!\n\n"
        "What are you looking for?",
        parse_mode="Markdown",
        reply_markup=store_category_keyboard()
    )


async def cmd_myorders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.get_user(user_id):
        await update.message.reply_text("❌ Register first with /start")
        return

    orders = db.get_user_orders(user_id)
    if not orders:
        await update.message.reply_text("🛒 No orders yet. Visit /store to browse products!")
        return

    msg = "📦 *Your Orders*\n\n"
    for o in orders:
        status_emoji = {'pending': '⏳', 'paid': '✅', 'cancelled': '❌'}.get(o['status'], '❓')
        delivered = "📬 Delivered" if o['delivery_sent'] else "⏳ Pending delivery"
        msg += (
            f"{status_emoji} *{o['item_name']}*\n"
            f"₦{o['amount']:,} · {o['status'].upper()} · {delivered}\n"
            f"Ref: `{o['paystack_reference']}`\n\n"
        )

    await update.message.reply_text(msg, parse_mode="Markdown")


async def handle_store_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("store:"):
        category = data.split("store:")[1]

        if category == "custom":
            db.set_state(user_id, "custom_order:describe", {})
            await query.message.reply_text(
                "🎛️ *Custom Order*\n\nDescribe exactly what you need:\n\n"
                "_(e.g. 'I need 200 contacts from UNILAG Computer Science 300L')_",
                parse_mode="Markdown",
                reply_markup=cancel_keyboard()
            )
            return

        items = db.get_store_items(item_type=category)
        if not items:
            await query.message.reply_text(f"😕 No {ITEM_TYPE_LABELS.get(category, category)} items available yet. Check back soon!")
            return

        for item in items:
            filter_info = ""
            if item.get('filter_school'):
                filter_info += f" · {item['filter_school']}"
            if item.get('filter_dept'):
                filter_info += f" · {item['filter_dept']}"
            if item.get('filter_level'):
                filter_info += f" · {item['filter_level']}"
            if item.get('filter_state'):
                filter_info += f" · {item['filter_state']}"

            await query.message.reply_text(
                f"📦 *{item['name']}*{filter_info}\n\n"
                f"{item['description'] or ''}\n\n"
                f"💰 *₦{item['price']:,}*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛒 Order", callback_data=f"buyitem:{item['id']}"),
                     InlineKeyboardButton("ℹ️ Info", callback_data=f"iteminfo:{item['id']}")]
                ])
            )

    elif data.startswith("buyitem:"):
        item_id = int(data.split(":")[1])
        item = db.get_store_item(item_id)
        if not item:
            await query.message.reply_text("❌ Item not found or no longer available.")
            return

        reference = generate_reference("ORD", user_id)
        try:
            acct = create_virtual_account(
                tx_ref=reference,
                amount=item['price'],
                narration=f"CampusConnect Store: {item['name']}",
                meta={'type': 'store', 'item_id': item_id, 'user_id': user_id}
            )
            db.create_order(user_id, item_id, item['item_type'], item['name'], item['price'], reference)

            await query.message.reply_text(
                format_payment_message(acct, f"Order: {item['name']}"),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Check Payment", callback_data=f"verifyorder:{reference}")]
                ])
            )
        except Exception as e:
            print(f"Store payment error: {e}")
            await query.message.reply_text("❌ Payment setup failed. Try again later.")

    elif data.startswith("verifyorder:"):
        reference = data.split(":")[1]
        from utils import verify_flw_payment
        paid, info = verify_flw_payment(reference)
        if paid:
            order = db.get_order_by_reference(reference)
            if order and order['status'] != 'paid':
                db.fulfill_order(reference)
                db.log_revenue(user_id, 'store', order['amount'], reference)
                await query.message.reply_text(
                    f"✅ *Payment Confirmed!*\n\nYour order for *{order['item_name']}* is being processed.\n"
                    f"You'll receive your item in this chat shortly!",
                    parse_mode="Markdown"
                )
                item = db.get_store_item(order['item_id'])
                if item and item.get('file_id'):
                    await context.bot.send_document(
                        user_id,
                        item['file_id'],
                        caption=f"📦 *{item['name']}*\n\nYour order has been delivered! Enjoy 🎉",
                        parse_mode="Markdown"
                    )
                    db.mark_delivered(order['id'])
                else:
                    await context.bot.send_message(
                        user_id,
                        "📬 Your order is being prepared by our team. You'll receive it within 24 hours."
                    )
                    admin_ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
                    for admin_id in admin_ids:
                        try:
                            await context.bot.send_message(
                                admin_id,
                                f"🛒 *New Order — Manual Delivery Needed*\n\n"
                                f"Item: {order['item_name']}\n"
                                f"User ID: {user_id}\n"
                                f"Amount: ₦{order['amount']:,}\n"
                                f"Order ID: {order['id']}\n\n"
                                f"Use /fulfillorder {order['id']} to mark as delivered.",
                                parse_mode="Markdown"
                            )
                        except Exception:
                            pass
            else:
                await query.message.reply_text("✅ This order is already paid and being processed.")
        else:
            await query.message.reply_text(
                "⏳ Payment not received yet.\n\nMake sure you transferred the exact amount, then try again.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Check Again", callback_data=f"verifyorder:{reference}")]
                ])
            )

    elif data.startswith("iteminfo:"):
        item_id = int(data.split(":")[1])
        item = db.get_store_item(item_id)
        if item:
            await query.answer(
                f"{item['name']}\n₦{item['price']:,}\n{item.get('description','')[:200]}",
                show_alert=True
            )


async def handle_custom_order_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state, data = db.get_state(user_id)

    if state == "custom_order:describe":
        text = update.message.text.strip()
        if text == "❌ Cancel":
            db.clear_state(user_id)
            await update.message.reply_text("Cancelled.", reply_markup=main_menu_keyboard())
            return True

        admin_ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
        user = db.get_user(user_id)
        for admin_id in admin_ids:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"🎛️ *Custom Order Request*\n\n"
                    f"From: {user['full_name']} (@{user.get('username','N/A')})\n"
                    f"School: {user['school']}\n"
                    f"User ID: {user_id}\n\n"
                    f"Request:\n{text}",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

        db.clear_state(user_id)
        await update.message.reply_text(
            "✅ *Custom order submitted!*\n\n"
            "Our team will review your request and get back to you within 24 hours with pricing and delivery details.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )
        return True

    return False
