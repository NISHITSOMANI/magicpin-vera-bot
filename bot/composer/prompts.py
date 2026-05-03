"""Prompt builders for the composer. Strict, grounded, deterministic."""
from __future__ import annotations
import json
from typing import Any
from ..decision.strategies import Strategy
from ..decision.voice import voice_for, language_for
from ..decision.facts import top_anchor_facts


SYSTEM_BASE = """You are Vera, magicpin's WhatsApp assistant for Indian merchants.

CORE RULES (violating any = automatic failure):
1. Use ONLY facts from the CONTEXT block. Never invent numbers, names, prices, dates, sources, competitors, distances, or research papers.
2. If a fact would strengthen the message but isn't in CONTEXT, omit it — don't fabricate.
3. Output ONLY a single JSON object, no markdown fences, no commentary. Keys: body, cta, rationale.
4. body must be ONE WhatsApp message: concise, specific, with ONE primary CTA in the last sentence.
5. Match the merchant's language preference exactly. "hi-en" = natural Hindi-English code-mix. "en" = English only.
6. Match the category voice exactly. Avoid taboo vocab (e.g., "guaranteed", "miracle", "best in city" for clinical categories).
7. Anchor on at least ONE concrete number, date, or named entity FROM CONTEXT. No generic claims like "X% off" without a real offer.
8. No multiple CTAs. No long preambles. No re-introductions if conversation_history shows prior turns.
9. For send_as=merchant_on_behalf: the message is from the merchant to their own customer — warm, no Vera self-reference.
10. cta must be one of: "binary_yes" | "binary_yes_stop" | "open_ended" | "info_only" | "slot_choice".

OUTPUT FORMAT (strict JSON):
{"body": "<message>", "cta": "<one of above>", "rationale": "<2-3 lines: why this trigger now, which fact anchored, which lever used>"}
"""


def _dump_context(obj: Any, max_chars: int) -> str:
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 24].rstrip() + "...<context_truncated>"


def _few_shot_block(few_shots: list[dict] | None) -> list[str]:
    if not few_shots:
        return []
    lines = ["", "FEW-SHOT EXAMPLES (style only; do not copy facts unless present in CONTEXT):"]
    for idx, shot in enumerate(few_shots, start=1):
        output = {
            "body": shot.get("body", ""),
            "cta": shot.get("cta", "binary_yes"),
            "rationale": shot.get("rationale", ""),
        }
        lines.extend(
            [
                f"--- EXAMPLE {idx} ({shot.get('category')}/{shot.get('trigger_kind')}, send_as={shot.get('send_as')}) ---",
                "LEVERS USED: " + ", ".join(str(x) for x in (shot.get("levers") or [])),
                "OUTPUT: " + json.dumps(output, ensure_ascii=False, sort_keys=True, default=str),
            ]
        )
    return lines


def build_user_prompt(category: dict | None, merchant: dict | None, trigger: dict | None,
                     customer: dict | None, strategy: Strategy,
                     few_shots: list[dict] | None = None) -> str:
    voice = voice_for(category)
    lang = language_for(merchant, customer)
    anchors = top_anchor_facts(merchant, trigger, category, customer, k=10)

    cat_min = {}
    if category:
        cat_min = {
            "slug": category.get("slug"),
            "voice": voice,
            "peer_stats": category.get("peer_stats"),
            "offer_catalog_titles": [o.get("title") for o in (category.get("offer_catalog") or [])[:8]],
            "digest": [
                {"title": d.get("title"), "source": d.get("source"),
                 "trial_n": d.get("trial_n"), "patient_segment": d.get("patient_segment")}
                for d in (category.get("digest") or [])[:5]
            ],
            "seasonal_beats": category.get("seasonal_beats"),
            "trend_signals": category.get("trend_signals"),
        }

    merch_min = {}
    if merchant:
        merch_min = {
            "identity": merchant.get("identity"),
            "performance": merchant.get("performance"),
            "offers": merchant.get("offers"),
            "customer_aggregate": merchant.get("customer_aggregate"),
            "signals": merchant.get("signals"),
            "review_themes": merchant.get("review_themes"),
            "subscription": merchant.get("subscription"),
            "conversation_history_last3": (merchant.get("conversation_history") or [])[-3:],
        }

    cust_min = customer if customer else None
    trig_min = trigger if trigger else None

    parts = [
        f"LANGUAGE: {lang}  (en = English only; hi-en = Hindi-English code-mix natural)",
        f"SEND_AS: {strategy.send_as}",
        f"STRATEGY: kind={strategy.kind}, levers={strategy.levers}, cta_shape={strategy.cta_shape}, max_chars={strategy.max_chars}",
        f"FRAMING_GUIDANCE: {strategy.framing}",
        "",
        "MUST-ANCHOR FACTS (pick 1-3, weave naturally; do not list):",
        *[f"  - {a}" for a in anchors],
        "",
        "CONTEXT.category:",
        _dump_context(cat_min, 3200),
        "",
        "CONTEXT.merchant:",
        _dump_context(merch_min, 3600),
        "",
        "CONTEXT.trigger:",
        _dump_context(trig_min, 2400),
    ]
    if cust_min:
        parts += ["", "CONTEXT.customer:", _dump_context(cust_min, 2200)]

    parts += _few_shot_block(few_shots)
    parts += [
        "",
        "TASK: Compose the next WhatsApp message under STRATEGY. Output ONLY the JSON object specified by the system rules.",
        f"Hard char target for body: ≤ {strategy.max_chars}. Be concrete and reply-friendly.",
    ]
    return "\n".join(parts)


SYSTEM_REPLY = """You are Vera in an active WhatsApp conversation with a merchant or customer.

DETERMINISTIC ACTIONS (must pick exactly one): "send" | "wait" | "end".
- "send": continue with a useful message. Provide body, cta, rationale.
- "wait": back off. Provide wait_seconds (300-3600) and rationale.
- "end": conversation done (not interested / completed / hostile / auto-reply confirmed).

RULES:
1. Detect auto-replies (verbatim repeats, generic "thank you for contacting us", "automated" text). After 1 attempt to bypass, end gracefully.
2. Detect intent transitions ("yes", "let's do it", "go ahead", "I want to join") — switch immediately to action mode (drafted artifact, no qualifying questions).
3. Never repeat your own previous message verbatim.
4. Stay grounded in CONTEXT. No fabrication.
5. Output ONLY one JSON object: {"action": "send|wait|end", "body": "...", "cta": "...", "wait_seconds": N, "rationale": "..."}
   For "wait" omit body/cta. For "end" omit body/cta/wait_seconds.
"""


def build_reply_prompt(category: dict | None, merchant: dict | None, trigger: dict | None,
                       customer: dict | None, conversation_turns: list[dict],
                       last_inbound: str, fsm_state: str, fsm_signal: str) -> str:
    parts = [
        f"FSM_STATE: {fsm_state}",
        f"DETECTED_SIGNAL: {fsm_signal}  (one of: normal, autoreply_suspected, intent_yes, hostile, off_topic, not_interested)",
        f"LAST_INBOUND: {last_inbound!r}",
        "",
        "CONVERSATION_TURNS (oldest→newest):",
        json.dumps(conversation_turns[-8:], ensure_ascii=False, default=str),
        "",
        "CONTEXT.category:", json.dumps(category, ensure_ascii=False, default=str)[:3500] if category else "null",
        "",
        "CONTEXT.merchant:", json.dumps(merchant, ensure_ascii=False, default=str)[:4000] if merchant else "null",
        "",
        "CONTEXT.trigger:", json.dumps(trigger, ensure_ascii=False, default=str) if trigger else "null",
    ]
    if customer:
        parts += ["", "CONTEXT.customer:", json.dumps(customer, ensure_ascii=False, default=str)]
    parts += ["", "Produce the JSON object now."]
    return "\n".join(parts)
