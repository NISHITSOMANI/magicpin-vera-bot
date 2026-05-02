"""Reply composer: handles /v1/reply. Uses FSM + LLM with grounding guard."""
from __future__ import annotations
import json
from .store import ConversationState, CONTEXT
from .conversation.fsm import step
from .conversation.detectors import hash_msg
from .composer.prompts import SYSTEM_REPLY, build_reply_prompt
from .composer.llm import call_llm
from .composer.guard import parse_json_loose, check_groundedness, voice_violations, normalize
from .decision.facts import numeric_anchors, named_entities, collect_strings
from .decision.voice import voice_for


def _ctx_for(state: ConversationState) -> tuple[dict | None, dict | None, dict | None, dict | None]:
    merchant = CONTEXT.get("merchant", state.merchant_id) if state.merchant_id else None
    category = None
    if merchant:
        category = CONTEXT.get("category", merchant.get("category_slug", ""))
    trigger = CONTEXT.get("trigger", state.trigger_id) if state.trigger_id else None
    customer = CONTEXT.get("customer", state.customer_id) if state.customer_id else None
    return category, merchant, trigger, customer


def respond(state: ConversationState, inbound: str, *, deadline_seconds: float = 22.0) -> dict:
    """Returns {"action": "send"|"wait"|"end", body?, cta?, wait_seconds?, rationale}."""
    next_action, signal = step(state, inbound)

    if next_action == "end":
        reasons = {
            "hostile": "Hostile reply detected; closing politely.",
            "not_interested": "Merchant signaled not interested; ending gracefully.",
            "autoreply_suspected": "Auto-reply confirmed across turns; routing to owner offline.",
            "off_topic": "Off-topic after one redirect; closing this thread.",
        }
        return {"action": "end", "rationale": reasons.get(signal, "Closing per FSM.")}

    category, merchant, trigger, customer = _ctx_for(state)

    # For hi-en/owner connect on first auto-reply strike, send a deterministic graceful nudge
    if signal == "autoreply_suspected" and state.autoreply_strikes == 1:
        body = "Samajh gayi — auto-reply lag raha hai. 1 chhota sa request: jab owner free ho, bas YES bhej dijiye, main 2 min mein kaam complete kar dungi."
        return {"action": "send", "body": body, "cta": "binary_yes",
                "rationale": "Single bypass attempt for suspected auto-reply (FSM strike 1)."}

    # Intent_yes: hard-route to pure action language (no qualifying questions).
    # This guarantees the action-mode contract regardless of LLM behavior.
    if signal == "intent_yes":
        # Try LLM first for richer action message; fallback if it slips into qualifying
        try:
            sys_p = SYSTEM_REPLY + "\n\nABSOLUTE RULE: This merchant just said YES. You must NOT ask any qualifying question. Lead with action verbs (Done / Sending / Drafting / Confirming / Booking). End with confirmation, not a question."
            turns = [{"role": t.role, "body": t.body, "ts": t.ts} for t in state.turns]
            usr = build_reply_prompt(category, merchant, trigger, customer, turns,
                                     inbound, state.state, signal)
            text, provider = call_llm(sys_p, usr, deadline_seconds=deadline_seconds)
            parsed = parse_json_loose(text) or {}
            cand = normalize(str(parsed.get("body", "") or ""))
            qualifying_words = ["would you", "do you ", "can you tell", "what if", "how about",
                                "shall we", "may i ask", "could you share"]
            actioning_words = ["done", "sending", "drafting", "drafted", "confirming",
                               "booking", "starting now", "on it"]
            cl = cand.lower()
            has_action = any(w in cl for w in actioning_words)
            has_qual = any(w in cl for w in qualifying_words)
            if cand and has_action and not has_qual:
                return {"action": "send", "body": cand,
                        "cta": str(parsed.get("cta", "info_only")),
                        "rationale": parsed.get("rationale", "Intent_yes routed to action mode (LLM)." )}
        except Exception:
            pass
        # Deterministic action-mode fallback
        return {"action": "send",
                "body": "Done — starting now. Drafting the next step and sending it in 2 min for your review.",
                "cta": "info_only",
                "rationale": "Intent_yes hard-routed to action mode (deterministic)."}

    if signal == "off_topic" and state.state == "off_topic_redirected":
        body = "Wo alag area hai, us mein main help nahi kar sakti. Wapas aate hain — listing/promo me se kya pehle dekhna chahenge?"
        return {"action": "send", "body": body, "cta": "open_ended",
                "rationale": "Single off-topic redirect; will end if asked again."}

    # LLM compose for normal / intent_yes
    sys = SYSTEM_REPLY
    turns = [{"role": t.role, "body": t.body, "ts": t.ts} for t in state.turns]
    usr = build_reply_prompt(category, merchant, trigger, customer, turns,
                             inbound, state.state, signal)
    try:
        text, provider = call_llm(sys, usr, deadline_seconds=deadline_seconds)
        parsed = parse_json_loose(text) or {}
        action = parsed.get("action", "send")
        if action not in ("send", "wait", "end"):
            action = "send"
        if action == "end":
            return {"action": "end", "rationale": parsed.get("rationale", "Model decided to end.")}
        if action == "wait":
            return {"action": "wait",
                    "wait_seconds": int(parsed.get("wait_seconds", 1800) or 1800),
                    "rationale": parsed.get("rationale", "Backing off.")}

        body = normalize(str(parsed.get("body", "") or ""))
        cta = str(parsed.get("cta", "open_ended") or "open_ended")

        if not body:
            raise RuntimeError("empty_body")

        # Anti-repetition vs last outbound
        if state.last_outbound_body and hash_msg(body) == hash_msg(state.last_outbound_body):
            body = body + " (Quick nudge — even a one-line yes/no helps.)"

        # Grounding guard
        allowed_nums = numeric_anchors(category, merchant, trigger, customer)
        names = named_entities(category, merchant, trigger, customer)
        for s in collect_strings(category, merchant, trigger, customer):
            for tok in s.split():
                names.add(tok.strip(",.;:!?()'\"").lower())
        ok, viol = check_groundedness(body, allowed_nums, names)
        if not ok:
            # Strip risky message; send a safe deterministic acknowledgement
            if signal == "intent_yes":
                body = "Done — starting now. Sending the draft in 2 min for your review."
                cta = "info_only"
            else:
                body = "Got it. Want me to send the next step now or schedule for tomorrow morning?"
                cta = "binary_yes"

        return {"action": "send", "body": body, "cta": cta,
                "rationale": parsed.get("rationale", f"signal={signal}; provider={provider}")}
    except Exception as e:
        # Deterministic fallback
        if signal == "intent_yes":
            return {"action": "send",
                    "body": "Done — starting now. Sending the first draft in 2 min for your review.",
                    "cta": "info_only",
                    "rationale": f"intent_yes routed to action mode; LLM error {type(e).__name__}"}
        return {"action": "send",
                "body": "Got it. Want me to send the next step now or schedule for tomorrow morning?",
                "cta": "binary_yes",
                "rationale": f"Deterministic fallback; signal={signal}; LLM error {type(e).__name__}"}
