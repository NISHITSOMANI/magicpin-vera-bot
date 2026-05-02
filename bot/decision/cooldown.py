"""Suppression-key memory + per-merchant cooldown."""
from __future__ import annotations
from datetime import datetime, timedelta
from ..store import SENT_SUPPRESSION_KEYS, LAST_SEND_TS


COOLDOWN_HOURS_BY_URGENCY = {1: 24, 2: 12, 3: 8, 4: 4, 5: 0}


def _parse(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return datetime.utcnow()


def is_suppressed(merchant_id: str, suppression_key: str) -> bool:
    return suppression_key in SENT_SUPPRESSION_KEYS.get(merchant_id, set())


def is_in_cooldown(merchant_id: str, now_iso: str, urgency: int) -> bool:
    last = LAST_SEND_TS.get(merchant_id)
    if not last:
        return False
    hours = COOLDOWN_HOURS_BY_URGENCY.get(urgency, 8)
    if hours <= 0:
        return False
    return _parse(now_iso) - _parse(last) < timedelta(hours=hours)


def mark_sent(merchant_id: str, suppression_key: str, now_iso: str) -> None:
    SENT_SUPPRESSION_KEYS.setdefault(merchant_id, set()).add(suppression_key)
    LAST_SEND_TS[merchant_id] = now_iso
