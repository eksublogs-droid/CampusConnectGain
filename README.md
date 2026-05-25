# CampusConnect Bot

Nigeria's student network — fully inside Telegram.
Student directory · Marketplace · Visibility channel · Ads system · Contact drops.

---

## ✅ 53 Tasks Completed

### Phase 1 — Foundation
- [x] Bot registration via BotFather
- [x] Railway + PostgreSQL setup docs
- [x] Full database schema (users, orders, drops, ads, broadcasts, revenue_log)
- [x] 8-step registration flow with confirmation
- [x] /myprofile command
- [x] /edit command — update any field
- [x] BotFather command menu (all commands)

### Phase 2 — Discovery
- [x] /directory — paginated browse
- [x] /findbyschool
- [x] /findbydept
- [x] /findbystate
- [x] /findbyinterest
- [x] /saved — bookmark profiles
- [x] /report — flag fake profiles
- [x] Connect button → contact card delivery

### Phase 3 — Channel & Visibility
- [x] Auto-post every new registration to channel
- [x] Channel integration setup

### Phase 4 — Admin Commands
- [x] /stats — platform stats
- [x] /broadcast — message all users
- [x] /lookup — find any user
- [x] /approve, /remove, /blacklist
- [x] /revenue — revenue dashboard
- [x] /export vcf
- [x] /export excel
- [x] Google Sheets auto-sync

### Phase 5 — Marketplace + Payments
- [x] Paystack API integration
- [x] /store — contact packs, group links, tools
- [x] /customorder flow
- [x] Auto-delivery after payment confirmed
- [x] /myorders
- [x] Webhook for payment confirmation

### Phase 6 — Contact Drop
- [x] /contactdrop free (new registrations, 3 days)
- [x] /contactdrop premium (₦500 — full database VCF)
- [x] 3-day auto-scheduler
- [x] /drophistory
- [x] /rundrop — manual admin trigger
- [x] /dropstats

### Phase 7 — Ads System
- [x] /runad — tier selection (Basic ₦500 / Standard ₦1,500 / Premium ₦4,000)
- [x] Ad copy + image upload flow
- [x] Preview before payment
- [x] Paystack payment → auto-publish to channel
- [x] Premium ad review queue (/adqueue)
- [x] /myadstatus — track active ads
- [x] Auto-expiry after duration ends

### Phase 8 — Polish & Launch
- [x] Error handling across all commands
- [x] Anti-spam protection
- [x] Rate limiting
- [x] Welcome message + menu keyboard
- [x] Railway deployment config

---

## 🚀 Setup Guide

### Step 1 — Create Your Bot
1. Open Telegram → search `@BotFather`
2. Send `/newbot`
3. Choose a name: **CampusConnect**
4. Choose username: e.g. `CampusConnectBot`
5. Copy the **BOT_TOKEN**

### Step 2 — Create the Channel
1. Create a new Telegram channel (e.g. `@CampusConnectNG`)
2. Add your bot as **admin** with "Post Messages" permission
3. Copy the channel username (e.g. `@CampusConnectNG`)

### Step 3 — Set Up Railway
1. Go to [railway.app](https://railway.app) → New Project
2. Add a **PostgreSQL** database
3. Copy the `DATABASE_URL` from the PostgreSQL service
4. Create a new service from GitHub or upload this code

### Step 4 — Configure Environment Variables

In Railway, set these variables:

```
BOT_TOKEN=your_bot_token_from_botfather
CHANNEL_ID=@CampusConnectNG
ADMIN_IDS=your_telegram_user_id
DATABASE_URL=postgresql://... (from Railway PostgreSQL)
PAYSTACK_SECRET_KEY=sk_live_xxx
PAYSTACK_PUBLIC_KEY=pk_live_xxx
WEBHOOK_URL=https://yourapp.railway.app
GOOGLE_SHEETS_ID=your_sheet_id (optional)
GOOGLE_CREDENTIALS_JSON={"type":"service_account",...} (optional)
```

> **How to get your Telegram user ID:** Message `@userinfobot` on Telegram.

### Step 5 — Set Up Paystack
1. Sign up at [paystack.com](https://paystack.com)
2. Go to Settings → API Keys & Webhooks
3. Copy your **Secret Key** and **Public Key**
4. Add webhook URL: `https://yourapp.railway.app/webhook/paystack`
5. Select event: `charge.success`

### Step 6 — Deploy
```bash
# Local test
pip install -r requirements.txt
cp .env.example .env
# Fill in your .env values
python main.py
```

For Railway: push to GitHub and Railway auto-deploys.

---

## 📁 File Structure

```
campusconnect/
├── main.py              # Bot entry point + handler routing
├── database.py          # All DB operations
├── schema.py            # PostgreSQL table definitions
├── utils.py             # VCF/Excel gen, Paystack, keyboards
├── admin.py             # All admin commands
├── webhook.py           # Paystack webhook Flask server
├── scheduler.py         # APScheduler (drops, ad expiry)
├── handlers/
│   ├── registration.py  # 8-step registration flow
│   ├── profile.py       # /myprofile, /edit
│   ├── directory.py     # /directory, /findby*, /saved, /report
│   ├── ads.py           # /runad, /myadstatus
│   ├── store.py         # /store, /myorders, /customorder
│   └── drops.py         # /contactdrop, /drophistory
├── requirements.txt
├── railway.toml
└── .env.example
```

---

## 💰 Revenue Streams

| Source | Amount |
|---|---|
| Basic Ad | ₦500/post |
| Standard Ad | ₦1,500/post |
| Premium Ad | ₦4,000/post |
| Premium Contact Drop | ₦500/cycle |
| Store — Contact Packs | ₦1,000–₦5,000 |
| Store — Group Links | ₦500–₦2,000 |
| Store — Tools | Custom |

---

## 🛠 Admin Commands Reference

| Command | Description |
|---|---|
| `/stats` | Platform stats (users, revenue, ads) |
| `/broadcast [msg]` | Message all users |
| `/lookup [query]` | Find any user |
| `/blacklist [id]` | Permanently ban user |
| `/remove [id]` | Deactivate user |
| `/approve [ad_id]` | Approve premium ad |
| `/adqueue` | Review pending premium ads |
| `/revenue` | Revenue breakdown |
| `/export vcf` | Export all contacts as VCF |
| `/export excel` | Export as Excel + sync Sheets |
| `/orders` | Pending store deliveries |
| `/fulfillorder [id]` | Mark order as delivered |
| `/rundrop` | Trigger manual contact drop |
| `/dropstats` | Drop subscriber counts |

---

## 📌 Notes

- **No /showcase command** — merged into /runad Basic (₦500). Basic tier IS the showcase.
- All payments via Paystack — webhook auto-confirms and triggers delivery.
- Premium ads go to admin review queue before publishing.
- Contact drops run automatically every 3 days via APScheduler.
- Google Sheets sync runs nightly (configure credentials to enable).

---

Built for EKSU & beyond · GlobalForgePodcast · EduGlobalForge
