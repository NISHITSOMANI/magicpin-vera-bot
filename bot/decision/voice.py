"""Per-category voice profile derivation."""
from __future__ import annotations
from typing import Any


CATEGORY_TONE_HINTS = {
    "dentists": "clinical-peer, source-citing, no overclaim, technical OK",
    "salons": "warm-practical, fellow-operator, light emojis allowed for customer",
    "restaurants": "operator-to-operator, covers/SKUs/channels vocabulary, time-bound",
    "gyms": "energetic-but-grounded, members/retention/programs vocabulary",
    "pharmacies": "utility-first, clinical-respectful, compliance-aware",
}


def voice_for(category: dict | None) -> dict:
    if not category:
        return {"tone": "professional", "vocab_taboo": [], "hint": "neutral"}
    voice = category.get("voice", {}) or {}
    return {
        "tone": voice.get("tone", "professional"),
        "register": voice.get("register", "respectful_collegial"),
        "vocab_allowed": voice.get("vocab_allowed", []) or [],
        "vocab_taboo": voice.get("vocab_taboo", []) or [],
        "salutation_examples": voice.get("salutation_examples", []) or [],
        "tone_examples": voice.get("tone_examples", []) or [],
        "hint": CATEGORY_TONE_HINTS.get(category.get("slug", ""), "professional"),
    }


def language_for(merchant: dict | None, customer: dict | None = None) -> str:
    """Returns 'en', 'hi-en', or 'en' default."""
    if customer:
        pref = (customer.get("identity") or {}).get("language_pref", "")
        if "hi" in pref.lower():
            return "hi-en"
        return "en"
    if not merchant:
        return "en"
    langs = (merchant.get("identity") or {}).get("languages", []) or []
    if "hi" in langs:
        return "hi-en"
    return "en"
