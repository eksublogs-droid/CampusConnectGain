"""
CampusConnect — Paystack Webhook Handler
Runs alongside the bot on the same process via threading.
"""
import os
import hmac
import hashlib
import json
import threading
from flask import Flask, request, jsonify
import database as db
from utils import verify_paystack_payment, AD_TIERS

app = Flask(__name__)
_bot_app = None  # set from main.py


def set_bot_app(application):
    global _bot_app
    _bot_app = application


@app.route("/webhook/paystack", methods=["POST"])
def paystack_webhook():
    secret = os.getenv("PAYSTACK_SECRET_KEY", "")
    signature = request.headers.get("X-Paystack-Signature", "")
    payload = request.get_data()

    # Verify signature
    expected = hmac.new(secret.encode(), payload, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(expected, signature or ""):
        return jsonify({"status": "invalid signature"}), 400

    event = json.loads(payload)
    event_type = event.get("event")
    data = event.get("data", {})

    if event_type == "charge.success":
        reference = data.get("reference")
        metadata = data.get("metadata", {})
        payment_type = metadata.get("type")

        if payment_type == "ad":
            handle_ad_payment(reference, metadata)
        elif payment_type == "store":
            handle_store_payment(reference, metadata)
        elif payment_type == "drop":
            handle_drop_payment(reference, metadata)

    return jsonify({"status": "ok"}), 200


def handle_ad_payment(reference, metadata):
    ad = db.get_ad_by_reference(reference)
    if not ad or ad['status'] != 'pending':
        return
    user_id = ad['user_id']
    tier = ad['tier']
    db.log_revenue(user_id, f"ad_{tier}", AD_TIERS.get(tier, {}).get('price', 0), reference)
    with db.db() as cur:
        cur.execute("UPDATE ads SET status='paid' WHERE paystack_reference=%s", (reference,))
    print(f"✅ Ad payment confirmed: {reference}")


def handle_store_payment(reference, metadata):
    order = db.get_order_by_reference(reference)
    if not order or order['status'] == 'paid':
        return
    db.fulfill_order(reference)
    db.log_revenue(order['user_id'], 'store', order['amount'], reference)
    print(f"✅ Store payment confirmed: {reference}")


def handle_drop_payment(reference, metadata):
    user_id = metadata.get('user_id')
    tier = metadata.get('tier', 'premium')
    if user_id:
        db.subscribe_drop(int(user_id), tier)
        db.log_revenue(int(user_id), f'drop_{tier}', 500, reference)
    print(f"✅ Drop payment confirmed: {reference}")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "bot": "CampusConnect"}), 200


def run_webhook_server():
    port = int(os.getenv("WEBHOOK_SERVER_PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)


def start_webhook_thread():
    t = threading.Thread(target=run_webhook_server, daemon=True)
    t.start()
    print(f"🌐 Webhook server started")
