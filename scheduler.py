"""
CampusConnect — Job Scheduler
Handles: 3-day contact drops, ad expiry
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import database as db

_scheduler = None


def start_scheduler(bot):
    global _scheduler
    _scheduler = AsyncIOScheduler()

    # Contact drop every 3 days at 9 AM
    _scheduler.add_job(
        _run_drop,
        'cron',
        day_of_week='*/3',
        hour=9,
        minute=0,
        args=[bot],
        id='contact_drop'
    )

    # Check ad expiry every hour
    _scheduler.add_job(
        _expire_ads,
        'interval',
        hours=1,
        args=[bot],
        id='expire_ads'
    )

    # Google Sheets sync daily at midnight
    _scheduler.add_job(
        _sync_sheets,
        'cron',
        hour=0,
        minute=0,
        id='sheets_sync'
    )

    _scheduler.start()
    print("⏰ Scheduler started")


async def _run_drop(bot):
    from handlers.drops import run_scheduled_drop
    await run_scheduled_drop(bot)


async def _expire_ads(bot):
    expired = db.get_expired_ads()
    channel_id = __import__('os').getenv("CHANNEL_ID")

    for ad in expired:
        db.expire_ad(ad['id'])
        print(f"⌛ Ad #{ad['id']} expired")
        # Optionally notify user
        try:
            await bot.send_message(
                ad['user_id'],
                f"⌛ *Your ad has ended*\n\nYour {ad['tier']} ad has expired.\nRun a new one with /runad!",
                parse_mode="Markdown"
            )
        except Exception:
            pass


async def _sync_sheets():
    from utils import sync_to_google_sheets
    users = db.get_all_users()
    success = sync_to_google_sheets(users)
    print(f"📊 Sheets sync: {'✅' if success else '❌'}")
