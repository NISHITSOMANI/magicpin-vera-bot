"""Decide which available trigger(s) to act on this tick."""
from __future__ import annotations
from .cooldown import is_suppressed, is_in_cooldown


def rank_triggers(triggers: list[dict], now_iso: str) -> list[dict]:
    """Sort triggers by (urgency desc, expires_at asc, id asc) deterministically."""
    def key(t: dict):
        return (-int(t.get("urgency", 1)), str(t.get("expires_at", "")), str(t.get("id", "")))
    return sorted(triggers, key=key)


def select_actionable(triggers: list[dict], now_iso: str, max_actions: int = 20) -> list[dict]:
    """Pick triggers we should send for: not suppressed, not in cooldown, one per merchant per tick."""
    seen_merchants: set[str] = set()
    chosen: list[dict] = []
    for trg in rank_triggers(triggers, now_iso):
        merchant_id = trg.get("merchant_id") or (trg.get("payload") or {}).get("merchant_id")
        if not merchant_id:
            continue
        if merchant_id in seen_merchants:
            continue
        sk = trg.get("suppression_key", "")
        urg = int(trg.get("urgency", 2))
        if sk and is_suppressed(merchant_id, sk):
            continue
        if is_in_cooldown(merchant_id, now_iso, urg):
            continue
        chosen.append(trg)
        seen_merchants.add(merchant_id)
        if len(chosen) >= max_actions:
            break
    return chosen
