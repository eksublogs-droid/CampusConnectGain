"""
CampusConnect — Database utilities
"""
import os
import json
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from schema import CREATE_TABLES_SQL

DATABASE_URL = os.getenv("DATABASE_URL")


def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


@contextmanager
def db():
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def init_db():
    with db() as cur:
        cur.execute(CREATE_TABLES_SQL)
    print("✅ Database initialized successfully")


# ───── USER OPERATIONS ─────

def get_user(user_id: int):
    with db() as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()


def create_user(data: dict):
    with db() as cur:
        cur.execute("""
            INSERT INTO users (id, username, full_name, phone, school, department, level, state, interests, bio, profile_photo_id)
            VALUES (%(id)s, %(username)s, %(full_name)s, %(phone)s, %(school)s, %(department)s, %(level)s, %(state)s, %(interests)s, %(bio)s, %(profile_photo_id)s)
            ON CONFLICT (id) DO UPDATE SET
                full_name=EXCLUDED.full_name, phone=EXCLUDED.phone, school=EXCLUDED.school,
                department=EXCLUDED.department, level=EXCLUDED.level, state=EXCLUDED.state,
                interests=EXCLUDED.interests, bio=EXCLUDED.bio, profile_photo_id=EXCLUDED.profile_photo_id,
                updated_at=NOW()
        """, data)


def update_user_field(user_id: int, field: str, value):
    allowed = {'full_name','phone','school','department','level','state','interests','bio','profile_photo_id','is_active','username'}
    if field not in allowed:
        raise ValueError(f"Field {field} not allowed")
    with db() as cur:
        cur.execute(f"UPDATE users SET {field} = %s, updated_at = NOW() WHERE id = %s", (value, user_id))


def get_all_users(active_only=True):
    with db() as cur:
        q = "SELECT * FROM users WHERE is_blacklisted = FALSE"
        if active_only:
            q += " AND is_active = TRUE"
        cur.execute(q)
        return cur.fetchall()


def search_users(school=None, dept=None, state=None, interest=None, limit=10, offset=0):
    conditions = ["is_active = TRUE", "is_blacklisted = FALSE"]
    params = []
    if school:
        conditions.append("LOWER(school) LIKE %s")
        params.append(f"%{school.lower()}%")
    if dept:
        conditions.append("LOWER(department) LIKE %s")
        params.append(f"%{dept.lower()}%")
    if state:
        conditions.append("LOWER(state) LIKE %s")
        params.append(f"%{state.lower()}%")
    if interest:
        conditions.append("LOWER(interests::text) LIKE %s")
        params.append(f"%{interest.lower()}%")
    where = " AND ".join(conditions)
    params += [limit, offset]
    with db() as cur:
        cur.execute(f"SELECT * FROM users WHERE {where} ORDER BY registered_at DESC LIMIT %s OFFSET %s", params)
        return cur.fetchall()


def count_users(school=None, dept=None, state=None):
    conditions = ["is_active = TRUE", "is_blacklisted = FALSE"]
    params = []
    if school:
        conditions.append("LOWER(school) LIKE %s"); params.append(f"%{school.lower()}%")
    if dept:
        conditions.append("LOWER(department) LIKE %s"); params.append(f"%{dept.lower()}%")
    if state:
        conditions.append("LOWER(state) LIKE %s"); params.append(f"%{state.lower()}%")
    where = " AND ".join(conditions)
    with db() as cur:
        cur.execute(f"SELECT COUNT(*) as c FROM users WHERE {where}", params)
        return cur.fetchone()['c']


def blacklist_user(user_id: int):
    with db() as cur:
        cur.execute("UPDATE users SET is_blacklisted = TRUE, is_active = FALSE WHERE id = %s", (user_id,))


def get_recent_users(days=3):
    with db() as cur:
        cur.execute("SELECT * FROM users WHERE registered_at >= NOW() - INTERVAL '%s days' AND is_active = TRUE AND is_blacklisted = FALSE", (days,))
        return cur.fetchall()


# ───── CONVERSATION STATE ─────

def set_state(user_id: int, state: str, data: dict = {}):
    with db() as cur:
        cur.execute("""
            INSERT INTO conversation_states (user_id, state, data, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (user_id) DO UPDATE SET state=EXCLUDED.state, data=EXCLUDED.data, updated_at=NOW()
        """, (user_id, state, json.dumps(data)))


def get_state(user_id: int):
    with db() as cur:
        cur.execute("SELECT state, data FROM conversation_states WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        if row:
            return row['state'], row['data'] if isinstance(row['data'], dict) else json.loads(row['data'])
        return None, {}


def clear_state(user_id: int):
    with db() as cur:
        cur.execute("DELETE FROM conversation_states WHERE user_id = %s", (user_id,))


# ───── SAVED PROFILES ─────

def save_profile(user_id: int, target_id: int):
    with db() as cur:
        cur.execute("INSERT INTO saved_profiles (user_id, saved_user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (user_id, target_id))


def get_saved(user_id: int):
    with db() as cur:
        cur.execute("""
            SELECT u.* FROM users u
            JOIN saved_profiles sp ON sp.saved_user_id = u.id
            WHERE sp.user_id = %s AND u.is_active = TRUE
            ORDER BY sp.saved_at DESC
        """, (user_id,))
        return cur.fetchall()


# ───── REPORTS ─────

def create_report(reporter_id: int, reported_id: int, reason: str):
    with db() as cur:
        cur.execute("INSERT INTO reports (reporter_id, reported_user_id, reason) VALUES (%s, %s, %s)", (reporter_id, reported_id, reason))


# ───── ORDERS ─────

def create_order(user_id: int, item_id: int, item_type: str, item_name: str, amount: int, reference: str):
    with db() as cur:
        cur.execute("""
            INSERT INTO orders (user_id, item_id, item_type, item_name, amount, paystack_reference)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        """, (user_id, item_id, item_type, item_name, amount, reference))
        return cur.fetchone()['id']


def get_order_by_reference(reference: str):
    with db() as cur:
        cur.execute("SELECT * FROM orders WHERE paystack_reference = %s", (reference,))
        return cur.fetchone()


def fulfill_order(reference: str):
    with db() as cur:
        cur.execute("UPDATE orders SET status='paid', paid_at=NOW() WHERE paystack_reference = %s", (reference,))


def mark_delivered(order_id: int):
    with db() as cur:
        cur.execute("UPDATE orders SET delivery_sent = TRUE WHERE id = %s", (order_id,))


def get_user_orders(user_id: int):
    with db() as cur:
        cur.execute("SELECT * FROM orders WHERE user_id = %s ORDER BY created_at DESC LIMIT 20", (user_id,))
        return cur.fetchall()


def get_pending_orders():
    with db() as cur:
        cur.execute("SELECT o.*, u.full_name, u.username FROM orders o JOIN users u ON u.id = o.user_id WHERE o.status = 'paid' AND o.delivery_sent = FALSE ORDER BY o.paid_at")
        return cur.fetchall()


# ───── STORE ITEMS ─────

def get_store_items(item_type=None):
    with db() as cur:
        q = "SELECT * FROM store_items WHERE is_active = TRUE"
        params = []
        if item_type:
            q += " AND item_type = %s"
            params.append(item_type)
        q += " ORDER BY id"
        cur.execute(q, params)
        return cur.fetchall()


def get_store_item(item_id: int):
    with db() as cur:
        cur.execute("SELECT * FROM store_items WHERE id = %s AND is_active = TRUE", (item_id,))
        return cur.fetchone()


def add_store_item(name, description, item_type, price, file_id=None, file_name=None, filter_school=None, filter_dept=None, filter_level=None, filter_state=None):
    with db() as cur:
        cur.execute("""
            INSERT INTO store_items (name, description, item_type, price, file_id, file_name, filter_school, filter_dept, filter_level, filter_state)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (name, description, item_type, price, file_id, file_name, filter_school, filter_dept, filter_level, filter_state))
        return cur.fetchone()['id']


# ───── CONTACT DROPS ─────

def subscribe_drop(user_id: int, tier: str):
    with db() as cur:
        cur.execute("""
            INSERT INTO drop_subscriptions (user_id, tier) VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """, (user_id, tier))


def get_drop_subscribers(tier=None):
    with db() as cur:
        if tier:
            cur.execute("SELECT * FROM drop_subscriptions WHERE is_active = TRUE AND tier = %s", (tier,))
        else:
            cur.execute("SELECT * FROM drop_subscriptions WHERE is_active = TRUE")
        return cur.fetchall()


def log_drop(user_id: int, tier: str, vcf_file_id: str, count: int):
    with db() as cur:
        cur.execute("INSERT INTO drop_history (user_id, tier, vcf_file_id, contacts_count) VALUES (%s,%s,%s,%s)", (user_id, tier, vcf_file_id, count))


def get_drop_history(user_id: int):
    with db() as cur:
        cur.execute("SELECT * FROM drop_history WHERE user_id = %s ORDER BY sent_at DESC LIMIT 10", (user_id,))
        return cur.fetchall()


# ───── ADS ─────

def create_ad(user_id, tier, ad_copy, amount, reference, image_file_id=None, video_file_id=None):
    with db() as cur:
        cur.execute("""
            INSERT INTO ads (user_id, tier, ad_copy, image_file_id, video_file_id, amount, paystack_reference)
            VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (user_id, tier, ad_copy, image_file_id, video_file_id, amount, reference))
        return cur.fetchone()['id']


def get_ad_by_reference(reference: str):
    with db() as cur:
        cur.execute("SELECT * FROM ads WHERE paystack_reference = %s", (reference,))
        return cur.fetchone()


def activate_ad(reference: str, message_id: int, duration_hours: int):
    with db() as cur:
        cur.execute("""
            UPDATE ads SET status='active', channel_message_id=%s,
            starts_at=NOW(), expires_at=NOW() + INTERVAL '%s hours'
            WHERE paystack_reference=%s
        """, (message_id, duration_hours, reference))


def get_user_ads(user_id: int):
    with db() as cur:
        cur.execute("SELECT * FROM ads WHERE user_id = %s ORDER BY created_at DESC LIMIT 10", (user_id,))
        return cur.fetchall()


def get_pending_ads():
    with db() as cur:
        cur.execute("""
            SELECT a.*, u.full_name, u.username FROM ads a
            JOIN users u ON u.id = a.user_id
            WHERE a.status = 'paid' AND a.tier = 'premium'
            ORDER BY a.created_at
        """)
        return cur.fetchall()


def get_expired_ads():
    with db() as cur:
        cur.execute("SELECT * FROM ads WHERE status = 'active' AND expires_at <= NOW()")
        return cur.fetchall()


def expire_ad(ad_id: int):
    with db() as cur:
        cur.execute("UPDATE ads SET status = 'expired' WHERE id = %s", (ad_id,))


def approve_ad(ad_id: int):
    with db() as cur:
        cur.execute("UPDATE ads SET status='paid' WHERE id=%s RETURNING *", (ad_id,))
        return cur.fetchone()


def reject_ad(ad_id: int, reason: str):
    with db() as cur:
        cur.execute("UPDATE ads SET status='rejected' WHERE id=%s", (ad_id,))


# ───── REVENUE ─────

def log_revenue(user_id: int, source: str, amount: int, reference: str = None):
    with db() as cur:
        cur.execute("INSERT INTO revenue_log (user_id, source, amount, reference) VALUES (%s,%s,%s,%s)", (user_id, source, amount, reference))


def get_revenue_stats():
    with db() as cur:
        cur.execute("""
            SELECT
                SUM(CASE WHEN created_at >= NOW() - INTERVAL '1 day' THEN amount ELSE 0 END) as today,
                SUM(CASE WHEN created_at >= NOW() - INTERVAL '7 days' THEN amount ELSE 0 END) as week,
                SUM(CASE WHEN created_at >= NOW() - INTERVAL '30 days' THEN amount ELSE 0 END) as month,
                SUM(amount) as total,
                source,
                COUNT(*) as tx_count
            FROM revenue_log
            GROUP BY source
        """)
        return cur.fetchall()


# ───── STATS ─────

def get_platform_stats():
    with db() as cur:
        cur.execute("""
            SELECT
                (SELECT COUNT(*) FROM users WHERE is_active=TRUE AND is_blacklisted=FALSE) as total_users,
                (SELECT COUNT(*) FROM users WHERE registered_at >= NOW() - INTERVAL '7 days') as new_this_week,
                (SELECT COUNT(*) FROM orders WHERE status='paid') as total_orders,
                (SELECT COALESCE(SUM(amount),0) FROM revenue_log) as total_revenue,
                (SELECT COUNT(*) FROM ads WHERE status='active') as active_ads,
                (SELECT COUNT(*) FROM drop_subscriptions WHERE is_active=TRUE) as drop_subscribers
        """)
        return cur.fetchone()


def get_users_by_school():
    with db() as cur:
        cur.execute("SELECT school, COUNT(*) as c FROM users WHERE is_active=TRUE GROUP BY school ORDER BY c DESC LIMIT 10")
        return cur.fetchall()


def get_users_by_state():
    with db() as cur:
        cur.execute("SELECT state, COUNT(*) as c FROM users WHERE is_active=TRUE GROUP BY state ORDER BY c DESC LIMIT 10")
        return cur.fetchall()


def lookup_user(query: str):
    with db() as cur:
        cur.execute("""
            SELECT * FROM users WHERE
            LOWER(full_name) LIKE %s OR LOWER(username) LIKE %s OR phone LIKE %s
            LIMIT 5
        """, (f"%{query.lower()}%", f"%{query.lower()}%", f"%{query}%"))
        return cur.fetchall()
