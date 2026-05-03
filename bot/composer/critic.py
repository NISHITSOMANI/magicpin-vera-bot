"""Self-critique and bounded revision pass for composed Vera messages."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ..decision.facts import collect_strings, named_entities, numeric_anchors
from ..decision.strategies import Strategy
from ..decision.voice import voice_for
from .guard import check_groundedness, check_groundedness_v2, normalize, parse_json_loose, voice_violations
from .llm import call_llm


CRITIC_CACHE: dict[str, tuple[str, str, dict[str, Any]]] = {}

SCORE_KEYS = [
    "specificity",
    "category_fit",
    "merchant_fit",
    "trigger_relevance",
    "engagement_compulsion",
]


SYSTEM_CRITIC = """You are Vera's deterministic quality critic.

Score the draft WhatsApp message against the magicpin rubric:
- specificity
- category_fit
- merchant_fit
- trigger_relevance
- engagement_compulsion

Use ONLY facts present in CONTEXT. If every score is >= 8, return the draft body and cta unchanged.
If any score is < 8, revise the body by fixing the weakest dimension first while preserving grounded facts and one clear CTA.
Never invent numbers, prices, dates, names, sources, competitors, buildings, medicines, batches, or offers.

Output ONLY strict JSON:
{"scores":{"specificity":0,"category_fit":0,"merchant_fit":0,"trigger_relevance":0,"engagement_compulsion":0},"revised":false,"body":"...","cta":"...","reason":"..."}
"""


def _cache_key(
    draft_body: str,
    draft_cta: str,
    category: dict | None,
    merchant: dict | None,
    trigger: dict | None,
    customer: dict | None,
    strategy: Strategy,
) -> str:
    obj = {
        "draft_body": draft_body,
        "draft_cta": draft_cta,
        "category": category or {},
        "merchant": merchant or {},
        "trigger": trigger or {},
        "customer": customer or {},
        "strategy": {
            "kind": strategy.kind,
            "levers": strategy.levers,
            "cta_shape": strategy.cta_shape,
            "send_as": strategy.send_as,
            "max_chars": strategy.max_chars,
        },
    }
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _clip(obj: Any, max_chars: int) -> str:
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 24].rstrip() + "...<context_truncated>"


def _build_prompt(
    draft_body: str,
    draft_cta: str,
    category: dict | None,
    merchant: dict | None,
    trigger: dict | None,
    customer: dict | None,
    strategy: Strategy,
) -> str:
    return "\n".join(
        [
            f"STRATEGY: kind={strategy.kind}, send_as={strategy.send_as}, levers={strategy.levers}, cta_shape={strategy.cta_shape}, max_chars={strategy.max_chars}",
            "",
            "DRAFT:",
            json.dumps({"body": draft_body, "cta": draft_cta}, ensure_ascii=False, sort_keys=True),
            "",
            "CONTEXT.category:",
            _clip(category or {}, 2600),
            "",
            "CONTEXT.merchant:",
            _clip(merchant or {}, 3200),
            "",
            "CONTEXT.trigger:",
            _clip(trigger or {}, 2200),
            "",
            "CONTEXT.customer:",
            _clip(customer or {}, 2200) if customer else "null",
            "",
            "Return the strict JSON now.",
        ]
    )


def _coerce_scores(value: Any) -> dict[str, int]:
    raw = value if isinstance(value, dict) else {}
    scores: dict[str, int] = {}
    for key in SCORE_KEYS:
        try:
            scores[key] = max(0, min(10, int(raw.get(key, 0))))
        except Exception:
            scores[key] = 0
    return scores


def _fact_tokens(category: dict | None, merchant: dict | None, trigger: dict | None, customer: dict | None) -> set[str]:
    tokens: set[str] = set()
    for text in collect_strings(category, merchant, trigger, customer):
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_.'-]{2,}", text):
            tokens.add(token.lower())
    return tokens


def _heuristic_scores(
    draft_body: str,
    category: dict | None,
    merchant: dict | None,
    trigger: dict | None,
    customer: dict | None,
    strategy: Strategy,
) -> dict[str, int]:
    body = draft_body or ""
    lower = body.lower()
    numbers = re.findall(r"\d+(?:\.\d+)?\s*%?|\b20\d{2}(?:-\d{2}-\d{2})?\b", body)
    facts = _fact_tokens(category, merchant, trigger, customer)
    fact_hits = sum(1 for token in facts if token and token in lower)
    trigger_kind = ((trigger or {}).get("kind") or strategy.kind or "").replace("_", " ")
    category_slug = ((category or {}).get("slug") or "").lower()
    merchant_ident = (merchant or {}).get("identity") or {}
    merchant_name = str(merchant_ident.get("name") or "").lower()
    owner_name = str(merchant_ident.get("owner_first_name") or "").lower()
    customer_name = str(((customer or {}).get("identity") or {}).get("name") or "").lower()

    domain_terms = {
        "dentists": ["patients", "fluoride", "caries", "recall", "cleaning", "clinic", "dental"],
        "restaurants": ["covers", "delivery", "thali", "swiggy", "zomato", "orders", "banner"],
        "gyms": ["members", "class", "conversion", "retention", "workout", "hiit", "attendance"],
        "salons": ["bridal", "skin", "slot", "service", "pricing", "salon", "wedding"],
        "pharmacies": ["refill", "medicines", "batch", "rx", "delivery", "dose", "replacement"],
    }
    specificity = 3 + min(5, len(numbers) * 2) + min(2, fact_hits // 3)
    category_fit = 7 + (1 if category_slug and category_slug.rstrip("s") in lower else 0)
    category_fit += 2 if any(word in lower for word in domain_terms.get(category_slug, [])) else 0
    merchant_fit = 4 + min(4, fact_hits // 2)
    if merchant_name and any(part in lower for part in merchant_name.split()[:2]):
        merchant_fit += 2
    if owner_name and owner_name in lower:
        merchant_fit += 2
    if customer_name and customer_name in lower:
        merchant_fit += 2
    trigger_relevance = 6 + (3 if trigger_kind and any(part in lower for part in trigger_kind.split()) else 0)
    trigger_relevance += min(3, fact_hits // 2)
    trigger_relevance += 2 if ((trigger or {}).get("kind") or strategy.kind) in lower.replace(" ", "_") else 0
    engagement = 5 + (2 if "?" in body else 0)
    engagement += 1 if any(phrase in lower for phrase in ("want me", "reply", "draft", "hold", "confirm")) else 0
    engagement += 1 if len(body) <= max(strategy.max_chars, 1) else -1

    return {
        "specificity": max(0, min(10, specificity)),
        "category_fit": max(0, min(10, category_fit)),
        "merchant_fit": max(0, min(10, merchant_fit)),
        "trigger_relevance": max(0, min(10, trigger_relevance)),
        "engagement_compulsion": max(0, min(10, engagement)),
    }


def _safe_revision(
    draft_body: str,
    draft_cta: str,
    category: dict | None,
    merchant: dict | None,
    trigger: dict | None,
    customer: dict | None,
    strategy: Strategy,
) -> tuple[str, str]:
    anchors: list[str] = []
    merchant_ident = (merchant or {}).get("identity") or {}
    customer_ident = (customer or {}).get("identity") or {}
    trigger_payload = (trigger or {}).get("payload") or {}

    name = (
        customer_ident.get("name")
        or merchant_ident.get("owner_first_name")
        or merchant_ident.get("name")
        or "there"
    )
    if name and name != "there":
        anchors.append(str(name))
    if (trigger or {}).get("kind"):
        anchors.append(str((trigger or {}).get("kind")).replace("_", " "))
    for source in (trigger_payload, (merchant or {}).get("performance") or {}, (merchant or {}).get("customer_aggregate") or {}):
        for key, value in source.items():
            if isinstance(value, (str, int, float)) and len(anchors) < 5:
                anchors.append(f"{key}={value}")
    if not anchors and draft_body:
        return draft_body, draft_cta

    body = (
        f"Hi {name}, quick Vera note on {anchors[1] if len(anchors) > 1 else strategy.kind}: "
        f"{'; '.join(anchors[2:5]) or 'there is one concrete next step from your latest context'}. "
        "Want me to draft the next WhatsApp/action note now?"
    )
    return body, "binary_yes"


def _passes_guard(
    body: str,
    category: dict | None,
    merchant: dict | None,
    trigger: dict | None,
    customer: dict | None,
) -> bool:
    contexts = {"category": category, "merchant": merchant, "trigger": trigger, "customer": customer}
    try:
        grounded_v2, _unsourced, _traced = check_groundedness_v2(body, contexts)
        if not grounded_v2:
            return False
    except Exception:
        grounded_v2 = None

    allowed_nums = numeric_anchors(category, merchant, trigger, customer)
    names = named_entities(category, merchant, trigger, customer)
    for text in collect_strings(category, merchant, trigger, customer):
        for tok in text.split():
            names.add(tok.strip(",.;:!?()'\"").lower())
    grounded, _violations = check_groundedness(body, allowed_nums, names)
    taboo = (voice_for(category) or {}).get("vocab_taboo", []) or []
    return (grounded or grounded_v2 is True) and not voice_violations(body, taboo)


def critique_and_revise(
    draft_body: str,
    draft_cta: str,
    category: dict | None,
    merchant: dict | None,
    trigger: dict | None,
    customer: dict | None,
    strategy: Strategy,
    *,
    deadline_seconds: float,
) -> tuple[str, str, dict]:
    """Score a draft and optionally return a grounded revision."""
    ck = _cache_key(draft_body, draft_cta, category, merchant, trigger, customer, strategy)
    if ck in CRITIC_CACHE:
        return CRITIC_CACHE[ck]

    prompt = _build_prompt(draft_body, draft_cta, category, merchant, trigger, customer, strategy)
    parsed: dict[str, Any] | None = None
    try:
        text, provider = call_llm(
            SYSTEM_CRITIC,
            prompt,
            deadline_seconds=max(6.0, deadline_seconds / 3.0),
        )
        parsed = parse_json_loose(text)
        if isinstance(parsed, dict):
            parsed.setdefault("provider", provider)
    except Exception:
        parsed = None

    if not parsed:
        scores = _heuristic_scores(draft_body, category, merchant, trigger, customer, strategy)
        if scores["specificity"] <= 4:
            body, cta = _safe_revision(draft_body, draft_cta, category, merchant, trigger, customer, strategy)
            parsed = {
                "scores": scores,
                "revised": body != draft_body,
                "body": body,
                "cta": cta,
                "reason": "Heuristic critic fallback: draft lacked concrete grounded anchors.",
                "provider": "heuristic",
            }
        else:
            parsed = {
                "scores": scores,
                "revised": False,
                "body": draft_body,
                "cta": draft_cta,
                "reason": "Heuristic critic fallback kept the draft.",
                "provider": "heuristic",
            }

    scores = _coerce_scores(parsed.get("scores"))
    body = normalize(str(parsed.get("body", "") or draft_body))
    cta = str(parsed.get("cta", "") or draft_cta).strip() or draft_cta
    any_weak = any(score < 8 for score in scores.values())

    if not any_weak:
        result = (draft_body, draft_cta, {**scores, "revised": False, "reason": parsed.get("reason", "")})
        CRITIC_CACHE[ck] = result
        return result

    if not body or body == draft_body:
        result = (draft_body, draft_cta, {**scores, "revised": False, "reason": parsed.get("reason", "")})
        CRITIC_CACHE[ck] = result
        return result

    if _passes_guard(body, category, merchant, trigger, customer):
        result = (
            body,
            cta,
            {**scores, "revised": True, "reason": parsed.get("reason", ""), "provider": parsed.get("provider", "")},
        )
    else:
        result = (
            draft_body,
            draft_cta,
            {
                **scores,
                "revised": False,
                "reason": "Critic revision failed grounding or voice guard; kept original draft.",
                "provider": parsed.get("provider", ""),
            },
        )
    CRITIC_CACHE[ck] = result
    return result
