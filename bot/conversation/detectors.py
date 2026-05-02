"""Auto-reply, intent-transition, hostile detectors. Pure rules + cheap LLM gate."""
from __future__ import annotations
import hashlib, re


AUTO_REPLY_PATTERNS = [
    r"thank you for contacting",
    r"we will get back",
    r"automated (response|message|reply)",
    r"i am (an? )?(automated|bot|virtual)",
    r"jaankari ke liye .*shukriya",
    r"team tak (pahuncha|forward)",
    r"out of office",
    r"away from (the )?(office|desk)",
    r"currently unavailable",
    r"hamari team .*pahuncha",
]


INTENT_YES_PATTERNS = [
    r"^\s*(yes|yeah|yep|haan|han|haa|ji|sure|okay|ok|theek|teek|done|ready|let'?s do it|go ahead|chalo|chaliye|do it|please|kar do|share kar do|send karo|bhejo|book karo|abhi karo)\b",
    r"^\s*(i (want|need)|mujhe|mujhko)\s+(join|sign up|register|start|chahiye|chahiye)",
    r"^\s*(start|begin|proceed|join)\b",
    r"^\s*(\+1|👍|✅|done|good)\b",
    r"yes\s+(send|please|do|kar|share)",
]


HOSTILE_PATTERNS = [
    r"\b(fuck|f\*ck|shit|bkl|bsdk|chutiy|madarc|behnc|gandu|bc|mc|bhosdi)",
    r"shut up", r"stop spamming", r"stop messaging",
    r"don'?t (call|message|text) (me|again)",
    r"block (you|this)", r"report you",
]


NOT_INTERESTED_PATTERNS = [
    r"^\s*(no|nope|nahi|nahin|na|nope|not interested|no thanks|no thank)\b",
    r"^\s*stop\b",
    r"don'?t want", r"not now", r"abhi nahi", r"baad mein", r"later",
]


OFF_TOPIC_PATTERNS = [
    r"\b(gst|income tax|loan|insurance|legal|lawyer|police)\b",
    r"\b(weather|cricket score|election|politics)\b",
]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def hash_msg(s: str) -> str:
    return hashlib.sha1(_norm(s).encode("utf-8")).hexdigest()[:16]


def _any_match(text: str, patterns: list[str]) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in patterns)


def detect(message: str, prior_inbound_hashes: list[str]) -> str:
    """Returns one of: 'autoreply_suspected', 'intent_yes', 'hostile', 'not_interested',
    'off_topic', 'normal'."""
    if not message or not message.strip():
        return "normal"
    h = hash_msg(message)
    # Verbatim repetition >= 1 prior occurrence in this conversation
    if h in prior_inbound_hashes:
        return "autoreply_suspected"
    if _any_match(message, AUTO_REPLY_PATTERNS):
        return "autoreply_suspected"
    if _any_match(message, HOSTILE_PATTERNS):
        return "hostile"
    if _any_match(message, NOT_INTERESTED_PATTERNS):
        return "not_interested"
    if _any_match(message, INTENT_YES_PATTERNS):
        return "intent_yes"
    if _any_match(message, OFF_TOPIC_PATTERNS):
        return "off_topic"
    return "normal"
