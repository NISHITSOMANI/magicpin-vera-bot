"""Pure compose(category, merchant, trigger, customer?) → ComposedMessage.

Hybrid: deterministic decision engine + LLM composer + grounding guard + template fallback.
Same-input → same-output (cached + temperature=0).
"""
from __future__ import annotations
import json, hashlib, time
from typing import Any

from .decision.strategies import for_trigger, Strategy
from .decision.voice import voice_for, language_for
from .decision.facts import top_anchor_facts, numeric_anchors, named_entities, collect_strings
from .composer.prompts import SYSTEM_BASE, build_user_prompt
from .composer.llm import call_llm
from .composer.guard import parse_json_loose, check_groundedness, voice_violations, normalize
from .composer import templates as templates_mod
from .store import COMPOSE_CACHE


VALID_CTAS = {"binary_yes", "binary_yes_stop", "open_ended", "info_only", "slot_choice"}


def _cache_key(category, merchant, trigger, customer) -> str:
    obj = {
        "c": (category or {}).get("slug"),
        "m": (merchant or {}).get("merchant_id"),
        "t": (trigger or {}).get("id"),
        "u": (customer or {}).get("customer_id") if customer else None,
        # Version stamps to invalidate cache when context updates
        "cv": json.dumps(category or {}, sort_keys=True, default=str)[-200:],
        "mv": json.dumps(merchant or {}, sort_keys=True, default=str)[-300:],
        "tv": json.dumps(trigger or {}, sort_keys=True, default=str)[-200:],
        "uv": json.dumps(customer or {}, sort_keys=True, default=str)[-200:] if customer else "",
    }
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def _truncate(s: str, n: int) -> str:
    s = s.strip()
    if len(s) <= n:
        return s
    cut = s[:n]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > n * 0.6 else cut).rstrip() + "…"


def compose(category: dict | None, merchant: dict | None, trigger: dict | None,
            customer: dict | None = None, *, deadline_seconds: float = 22.0) -> dict:
    """Compose a message. Returns dict with body, cta, send_as, suppression_key, rationale, meta."""
    ck = _cache_key(category, merchant, trigger, customer)
    if ck in COMPOSE_CACHE:
        return COMPOSE_CACHE[ck]

    strategy = for_trigger(trigger)
    voice = voice_for(category)
    lang = language_for(merchant, customer)
    suppression_key = (trigger or {}).get("suppression_key", "")
    fallback_used = False
    provider_used = "none"

    # Build allow-lists for grounding
    allowed_nums = numeric_anchors(category, merchant, trigger, customer)
    allowed_names_caps = named_entities(category, merchant, trigger, customer)
    # Also lowercase tokens
    name_pool: set[str] = set(allowed_names_caps)
    for s in collect_strings(category, merchant, trigger, customer):
        for tok in s.split():
            name_pool.add(tok.strip(",.;:!?()'\"").lower())
    taboo = voice.get("vocab_taboo", []) or []

    body = ""
    cta = "binary_yes"
    rationale_parts: list[str] = []

    # --- LLM attempt with guard ---
    try:
        sys = SYSTEM_BASE
        usr = build_user_prompt(category, merchant, trigger, customer, strategy)
        text, provider_used = call_llm(sys, usr, deadline_seconds=deadline_seconds)
        parsed = parse_json_loose(text) or {}
        cand_body = normalize(str(parsed.get("body", "") or ""))
        cand_cta = str(parsed.get("cta", "") or "").strip()
        cand_rationale = str(parsed.get("rationale", "") or "").strip()

        if cand_body and cand_cta in VALID_CTAS:
            grounded, violations = check_groundedness(cand_body, allowed_nums, name_pool)
            tabu_hits = voice_violations(cand_body, taboo)
            if grounded and not tabu_hits:
                body = _truncate(cand_body, strategy.max_chars)
                cta = cand_cta
                rationale_parts.append(cand_rationale or f"Trigger {strategy.kind}; levers={','.join(strategy.levers)}.")
            else:
                # Single repair pass — strip flagged items by asking model to re-anchor strictly
                repair_sys = SYSTEM_BASE + "\n\nPREVIOUS DRAFT FAILED GROUNDING. You may ONLY use facts that appear in CONTEXT. Remove any number, name, or claim not in CONTEXT."
                repair_usr = usr + f"\n\nPREVIOUS_DRAFT_BODY: {cand_body}\nVIOLATIONS: numbers={[v for v in violations if v.startswith('unknown_number')]}; names={[v for v in violations if v.startswith('unknown_name')]}; taboo={tabu_hits}\nReturn the corrected JSON only."
                try:
                    text2, provider_used2 = call_llm(repair_sys, repair_usr, deadline_seconds=max(6.0, deadline_seconds / 2))
                    p2 = parse_json_loose(text2) or {}
                    b2 = normalize(str(p2.get("body", "") or ""))
                    c2 = str(p2.get("cta", "") or "").strip()
                    if b2 and c2 in VALID_CTAS:
                        ok2, _ = check_groundedness(b2, allowed_nums, name_pool)
                        tab2 = voice_violations(b2, taboo)
                        if ok2 and not tab2:
                            body = _truncate(b2, strategy.max_chars)
                            cta = c2
                            provider_used = provider_used2
                            rationale_parts.append(p2.get("rationale", "") or f"Repair pass; trigger={strategy.kind}.")
                except Exception:
                    pass
    except Exception as e:
        rationale_parts.append(f"llm_error:{type(e).__name__}")

    # --- Template fallback ---
    if not body:
        fallback_used = True
        body, cta = templates_mod.render(category, merchant, trigger, customer)
        body = _truncate(body, strategy.max_chars)
        rationale_parts.append(f"Template fallback for trigger={strategy.kind} (LLM unavailable or ungrounded).")

    # Coerce cta to strategy default if mismatched shape
    if cta not in VALID_CTAS:
        cta = "binary_yes"

    # Build rationale (decision-engine trace)
    perf_anchor = ""
    if merchant:
        perf = merchant.get("performance") or {}
        if perf:
            perf_anchor = f"perf views={perf.get('views')}, ctr={perf.get('ctr')}"
    trace = (
        f"trigger={strategy.kind}/urgency={(trigger or {}).get('urgency','?')}; "
        f"levers={','.join(strategy.levers)}; cta_shape={strategy.cta_shape}; "
        f"voice={voice.get('tone','?')}/{lang}; "
        f"send_as={strategy.send_as}; "
        f"{perf_anchor}; "
        f"provider={provider_used}{'+template' if fallback_used else ''}."
    )
    rationale = (rationale_parts[0] if rationale_parts else "") + " | " + trace

    result = {
        "body": body,
        "cta": cta,
        "send_as": strategy.send_as,
        "suppression_key": suppression_key,
        "rationale": rationale.strip(" |"),
        "meta": {
            "strategy_kind": strategy.kind,
            "levers": strategy.levers,
            "language": lang,
            "provider": provider_used,
            "fallback_used": fallback_used,
        },
    }
    COMPOSE_CACHE[ck] = result
    return result
