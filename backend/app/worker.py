from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "syncrofin",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # E11 — idempotent job queue: acknowledge after execution so a killed
    # worker re-delivers the task instead of silently dropping it.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    result_expires=86400,  # 24 h
    worker_prefetch_multiplier=1,
    # Store the beat schedule in /tmp so it works in ephemeral containers
    # (replicas: 1 in Helm/Compose; the singleton guarantee comes from not
    # scaling beat, not from filesystem locking).
    beat_schedule_filename="/tmp/celerybeat-schedule",
)

celery_app.conf.beat_schedule = {
    "sync-all-connections-hourly": {
        "task": "app.tasks.sync_tasks.sync_all_connections",
        "schedule": 60 * 60,  # every hour; task itself skips connections synced < 4h ago
    },
    "generate-recurring-daily": {
        "task": "app.tasks.recurring_tasks.generate_all_recurring",
        "schedule": 60 * 60,  # every hour; generate_pending is idempotent (advances next_occurrence)
    },
    "apply-asset-growth-daily": {
        "task": "app.tasks.asset_tasks.apply_asset_growth_rules",
        "schedule": 60 * 60,  # every hour; idempotent (checks last value date)
    },
    "refresh-market-prices-daily": {
        "task": "app.tasks.asset_tasks.refresh_market_prices",
        # Once a day is enough for personal portfolio tracking — keeps us
        # well under Yahoo's unofficial per-IP caps and avoids the bot
        # heuristics that trip on a chatty schedule. Task upserts today's
        # AssetValue so history stays at one row per day per asset.
        "schedule": 60 * 60 * 24,
    },
    "sync-fx-rates-daily": {
        "task": "app.tasks.fx_rate_tasks.sync_fx_rates",
        "schedule": 60 * 60 * 12,  # twice daily (~60 API calls/month)
    },
    "restamp-recurring-fx-daily": {
        "task": "app.tasks.fx_rate_tasks.restamp_recurring_fx",
        "schedule": 60 * 60 * 12,  # twice daily, after FX rate sync
    },
    "generate-notifications-hourly": {
        "task": "app.tasks.notification_tasks.generate_notifications",
        # Idempotent: every notification is keyed on the situation it describes,
        # so an hourly run tells nobody the same thing twice.
        "schedule": 60 * 60,
    },
    "seal-audit-events-minutely": {
        "task": "app.tasks.audit_tasks.seal_audit_events",
        # Puts the events of the last minute into the tamper-evident chain. Reading or
        # exporting the trail seals too, so this only bounds how long a row stays unsealed.
        "schedule": 60,
    },
    "purge-access-log-daily": {
        "task": "app.tasks.audit_tasks.purge_access_log",
        # Anonymises access records older than the retention period (`access_log_retention_days`).
        # At a fixed time, not an interval: a beat restarted more often than daily would never reach it.
        "schedule": crontab(hour=3, minute=30),
    },
    "auto-apply-reconciliation-hourly": {
        "task": "app.tasks.reconciliation_tasks.auto_apply_suggestions",
        # Only touches workspaces that set a confidence bar; a no-op for the rest.
        "schedule": 60 * 60,
    },
    "restamp-fallback-fx-daily": {
        "task": "app.tasks.fx_rate_tasks.restamp_fallback_fx",
        # Twice daily, after FX rate sync — heals transactions that were
        # stamped with the 1:1 fallback (or left NULL) once real rates land.
        "schedule": 60 * 60 * 12,
    },
    "post-due-accruals-monthly": {
        "task": "app.tasks.accrual_tasks.post_due_accruals",
        "schedule": crontab(day_of_month=1, hour=4, minute=0),
    },
    "check-pending-payments": {
        "task": "app.tasks.payment_tasks.check_pending_payments",
        "schedule": 5 * 60,
    },
    "purge-expired-data-daily": {
        "task": "purge-expired-data",
        "schedule": crontab(hour=2, minute=0),
    },
}

celery_app.conf.include = [
    "app.tasks.sync_tasks",
    "app.tasks.recurring_tasks",
    "app.tasks.asset_tasks",
    "app.tasks.fx_rate_tasks",
    "app.tasks.notification_tasks",
    "app.tasks.reconciliation_tasks",
    "app.tasks.audit_tasks",
    "app.tasks.retention_tasks",
    "app.tasks.erp_tasks",
    "app.tasks.accrual_tasks",
    "app.tasks.payment_tasks",
    # Optional agents module — registering the import is harmless when
    # AGENTS_ENABLED=false (the task just won't be dispatched).
    "app.agents.tasks.ingest",
]

# Background jobs write too; their changes belong in the audit trail (as "system").
from app.core import audit  # noqa: E402,F401
