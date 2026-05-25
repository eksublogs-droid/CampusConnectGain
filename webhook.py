"""
CampusConnect — Flutterwave Webhook Handler
Runs alongside the bot on the same process via threading.
"""
import os
import json
import threading
from flask import Flask, request, jsonify, send_from_directory
import database as db
from utils import verify_flw_signature, AD_TIERS

app = Flask(__name__)
_bot_app = None  # set from main.py

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), "webapp")


def set_bot_app(application):
    global _bot_app
    _bot_app = application


@app.route("/register.html")
def serve_register():
    return send_from_directory(WEBAPP_DIR, "register.html")


@app.route("/webhook/flutterwave", methods=["POST"])
def flutterwave_webhook():
    signature = request.headers.get("verif-hash", "")
    payload = request.get_data()

    if not verify_flw_signature(payload, signature):
        return jsonify({"status": "invalid signature"}), 400

    try:
        event = json.loads(payload)
    except Exception:
        return jsonify({"status": "bad json"}), 400

    # Flutterwave sends event as top-level "event" key
    event_type = event.get("event", "")
    data = event.get("data", {})

    if event_type == "charge.completed" and data.get("status") == "successful":
        tx_ref = data.get("tx_ref", "")
        meta = data.get("meta") or {}

        payment_type = meta.get("type") or _infer_type_from_ref(tx_ref)

        if payment_type == "ad":
            handle_ad_payment(tx_ref, data, meta)
        elif payment_type == "store":
            handle_store_payment(tx_ref, data, meta)
        elif payment_type == "drop":
            handle_drop_payment(tx_ref, data, meta)

    return jsonify({"status": "ok"}), 200


def _infer_type_from_ref(tx_ref: str) -> str:
    """Fallback: infer payment type from reference prefix."""
    prefix = tx_ref.split("_")[0].upper()
    if prefix == "AD":
        return "ad"
    if prefix == "ORD":
        return "store"
    if prefix == "DROP":
        return "drop"
    return ""


def handle_ad_payment(tx_ref: str, data: dict, meta: dict):
    ad = db.get_ad_by_reference(tx_ref)
    if not ad or ad['status'] != 'pending':
        return
    user_id = ad['user_id']
    tier = ad['tier']
    db.log_revenue(user_id, f"ad_{tier}", AD_TIERS.get(tier, {}).get('price', 0), tx_ref)
    with db.db() as cur:
        cur.execute("UPDATE ads SET status='paid' WHERE paystack_reference=%s", (tx_ref,))
    print(f"✅ Ad payment confirmed: {tx_ref}")


def handle_store_payment(tx_ref: str, data: dict, meta: dict):
    order = db.get_order_by_reference(tx_ref)
    if not order or order['status'] == 'paid':
        return
    db.fulfill_order(tx_ref)
    db.log_revenue(order['user_id'], 'store', order['amount'], tx_ref)
    print(f"✅ Store payment confirmed: {tx_ref}")


def handle_drop_payment(tx_ref: str, data: dict, meta: dict):
    user_id = meta.get('user_id')
    tier = meta.get('tier', 'premium')
    if user_id:
        db.subscribe_drop(int(user_id), tier)
        db.log_revenue(int(user_id), f'drop_{tier}', 500, tx_ref)
    print(f"✅ Drop payment confirmed: {tx_ref}")


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
