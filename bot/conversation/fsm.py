"""Conversation FSM: maps detected signal + state → next action shape."""
from __future__ import annotations
from ..store import ConversationState, MERCHANT_AUTO_HASHES, MERCHANT_AUTO_STRIKES
from .detectors import detect, hash_msg


def step(state: ConversationState, inbound: str) -> tuple[str, str]:
    """Returns (next_action, signal). next_action ∈ {send, wait, end}.

    Updates state in place (FSM transitions, autoreply_strikes, hashes).
    Auto-reply tracking spans conversations per merchant_id.
    """
    mid = state.merchant_id or "unknown"
    prior_global = MERCHANT_AUTO_HASHES.get(mid, [])
    h = hash_msg(inbound)

    # Detect using BOTH per-conversation and per-merchant prior hashes
    combined_priors = list(state.inbound_hashes) + prior_global
    signal = detect(inbound, combined_priors)
    state.inbound_hashes.append(h)

    if signal == "autoreply_suspected":
        # Track per-merchant
        MERCHANT_AUTO_HASHES.setdefault(mid, []).append(h)
        MERCHANT_AUTO_STRIKES[mid] = MERCHANT_AUTO_STRIKES.get(mid, 0) + 1
        state.autoreply_strikes = MERCHANT_AUTO_STRIKES[mid]
        if state.autoreply_strikes >= 2:
            state.state = "closed"
            return "end", signal
        return "send", signal

    if signal == "hostile":
        state.state = "closed"
        return "end", signal

    if signal == "not_interested":
        state.state = "closed"
        return "end", signal

    if signal == "intent_yes":
        state.state = "action"
        return "send", signal

    if signal == "off_topic":
        # Polite single redirect; if asked again next turn, end
        if state.state == "off_topic_redirected":
            state.state = "closed"
            return "end", signal
        state.state = "off_topic_redirected"
        return "send", signal

    # normal
    state.state = "qualifying" if state.state in ("opened", "off_topic_redirected") else state.state
    return "send", signal
