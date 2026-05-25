"""
CampusConnect — Database Schema
Run this once to initialize all tables.
"""

CREATE_TABLES_SQL = """

-- USERS TABLE
CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    username TEXT,
    full_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    whatsapp_number TEXT,
    date_of_birth DATE,
    show_whatsapp BOOLEAN DEFAULT TRUE,
    school TEXT NOT NULL,
    department TEXT NOT NULL,
    level TEXT NOT NULL,
    state TEXT NOT NULL,
    interests TEXT[],
    bio TEXT,
    profile_photo_id TEXT,
    is_verified BOOLEAN DEFAULT FALSE,
    is_blacklisted BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    registered_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- SAVED PROFILES
CREATE TABLE IF NOT EXISTS saved_profiles (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    saved_user_id BIGINT REFERENCES users(id),
    saved_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, saved_user_id)
);

-- CONNECT REQUESTS
CREATE TABLE IF NOT EXISTS connect_requests (
    id SERIAL PRIMARY KEY,
    from_user_id BIGINT REFERENCES users(id),
    to_user_id BIGINT REFERENCES users(id),
    status TEXT DEFAULT 'pending',
    message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- REPORTS
CREATE TABLE IF NOT EXISTS reports (
    id SERIAL PRIMARY KEY,
    reporter_id BIGINT REFERENCES users(id),
    reported_user_id BIGINT REFERENCES users(id),
    reason TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ORDERS
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    item_id INTEGER,
    item_type TEXT,
    item_name TEXT,
    amount INTEGER NOT NULL,
    status TEXT DEFAULT 'pending',
    paystack_reference TEXT UNIQUE,
    delivery_sent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    paid_at TIMESTAMP
);

-- STORE ITEMS
CREATE TABLE IF NOT EXISTS store_items (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    item_type TEXT NOT NULL,
    price INTEGER NOT NULL,
    file_id TEXT,
    file_name TEXT,
    filter_school TEXT,
    filter_dept TEXT,
    filter_level TEXT,
    filter_state TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- CONTACT DROPS
CREATE TABLE IF NOT EXISTS drop_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    tier TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    subscribed_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS drop_history (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    tier TEXT NOT NULL,
    vcf_file_id TEXT,
    contacts_count INTEGER,
    sent_at TIMESTAMP DEFAULT NOW()
);

-- ADS
CREATE TABLE IF NOT EXISTS ads (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    tier TEXT NOT NULL,
    ad_copy TEXT NOT NULL,
    image_file_id TEXT,
    video_file_id TEXT,
    amount INTEGER NOT NULL,
    status TEXT DEFAULT 'pending',
    paystack_reference TEXT UNIQUE,
    channel_message_id BIGINT,
    starts_at TIMESTAMP,
    expires_at TIMESTAMP,
    impressions INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- CONVERSATION STATES (for multi-step flows)
CREATE TABLE IF NOT EXISTS conversation_states (
    user_id BIGINT PRIMARY KEY,
    state TEXT,
    data JSONB DEFAULT '{}',
    updated_at TIMESTAMP DEFAULT NOW()
);

-- REVENUE LOG
CREATE TABLE IF NOT EXISTS revenue_log (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    source TEXT NOT NULL,
    amount INTEGER NOT NULL,
    reference TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- BROADCASTS
CREATE TABLE IF NOT EXISTS broadcasts (
    id SERIAL PRIMARY KEY,
    admin_id BIGINT NOT NULL,
    message TEXT NOT NULL,
    sent_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- INDEXES
CREATE INDEX IF NOT EXISTS idx_users_school ON users(school);
CREATE INDEX IF NOT EXISTS idx_users_state ON users(state);
CREATE INDEX IF NOT EXISTS idx_users_dept ON users(department);
CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active);
CREATE INDEX IF NOT EXISTS idx_ads_status ON ads(status);
CREATE INDEX IF NOT EXISTS idx_ads_expires ON ads(expires_at);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_reference ON orders(paystack_reference);
"""

# Run once on existing databases to add new columns
MIGRATION_SQL = """
ALTER TABLE users ADD COLUMN IF NOT EXISTS whatsapp_number TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS date_of_birth DATE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS show_whatsapp BOOLEAN DEFAULT TRUE;
CREATE INDEX IF NOT EXISTS idx_users_dob ON users(date_of_birth);
"""
