"""Boucle de planification sans dépendance externe : règlement puis grille quotidienne à l'heure
configurée (fuseau EDGEBET_TIMEZONE), et écoute des réponses Telegram en parallèle.

Alternative : laisser n8n (ou cron) appeler `POST /api/pipeline/run?notify=true`.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

from edgebet.config import Settings

log = logging.getLogger(__name__)


def main_loop(s: Settings, once: bool = False) -> None:
    from edgebet.db.session import init_db
    from edgebet.pipeline.daily import run_daily
    from edgebet.pipeline.settle import run_settle

    init_db(s.db_url)
    tz = ZoneInfo(s.timezone)
    stop = threading.Event()
    if s.telegram_bot_token:
        from edgebet.notify.telegram import poll_forever

        threading.Thread(target=poll_forever, args=(s, stop), daemon=True, name="telegram-poll").start()
    last_run: date | None = None
    log.info("Worker démarré : grille quotidienne à %02d:%02d (%s)", s.notify_hour, s.notify_minute, s.timezone)
    while True:
        now = datetime.now(tz)
        due = (now.hour, now.minute) >= (s.notify_hour, s.notify_minute)
        if due and last_run != now.date():
            last_run = now.date()
            try:
                log.info("Règlement des paris passés…")
                run_settle(s, now=now)
            except Exception as exc:
                log.exception("Règlement en échec : %s", exc)
            try:
                res = run_daily(s, now=now, notify=bool(s.telegram_bot_token and s.telegram_chat_id))
                log.info("Grille : %s (crédits restants : %s)", res.message, res.credits_remaining)
                for w in res.warnings:
                    log.warning(w)
            except Exception as exc:
                log.exception("Pipeline quotidien en échec : %s", exc)
                if s.telegram_bot_token and s.telegram_chat_id:
                    try:
                        from edgebet.notify.telegram import send_text

                        send_text(s, f"⚠️ EdgeBet : pipeline en échec : {exc}")
                    except Exception:  # pragma: no cover
                        pass
        if once:
            stop.set()
            return
        time.sleep(30)
