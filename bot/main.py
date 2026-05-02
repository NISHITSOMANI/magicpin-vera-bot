"""FastAPI app — 5 endpoints required by the magicpin judge harness."""
from __future__ import annotations
import os, time, uuid
from datetime import datetime
from typing import Any
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Load .env if present (no hard dep on python-dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from .store import CONTEXT, CONVOS, ConversationTurn
from .compose import compose
from .reply import respond
from .decision.router import select_actionable
from .decision.cooldown import mark_sent

app = FastAPI(title="Vera Bot — magicpin AI Challenge")
START = time.time()

TEAM_NAME = os.getenv("TEAM_NAME", "Nishit Somani")
TEAM_EMAIL = os.getenv("TEAM_EMAIL", "somaninishit36@gmail.com")
TEAM_VERSION = os.getenv("TEAM_VERSION", "1.0.0")


# ----------------------- /v1/healthz -----------------------
@app.get("/v1/healthz")
async def healthz():
    return {"status": "ok",
            "uptime_seconds": int(time.time() - START),
            "contexts_loaded": CONTEXT.counts()}


# ----------------------- /v1/metadata -----------------------
@app.get("/v1/metadata")
async def metadata():
    return {
        "team_name": TEAM_NAME,
        "team_members": [TEAM_NAME],
        "model": "gemini-2.5-flash + groq-llama-3.3-70b + openrouter-deepseek-v3 (multi-provider router)",
        "approach": (
            "Deterministic decision engine (trigger router → strategy → levers → CTA shape) + "
            "LLM composer with allowed-facts grounding guard + voice/taboo enforcement + "
            "template fallback per (category × trigger). Conversation FSM with auto-reply hash "
            "detection, intent-transition routing, hostile/off-topic single-redirect-then-end. "
            "Per-merchant cooldown + suppression-key memory for restraint. "
            "compose() is a pure function shared by /v1/tick, /v1/reply, and offline submission.jsonl."
        ),
        "contact_email": TEAM_EMAIL,
        "version": TEAM_VERSION,
        "submitted_at": "2026-04-29T00:00:00Z",
    }


# ----------------------- /v1/context -----------------------
class CtxBody(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str | None = None


@app.post("/v1/context")
async def push_context(body: CtxBody):
    if body.scope not in ("category", "merchant", "customer", "trigger"):
        return JSONResponse(status_code=400,
                            content={"accepted": False, "reason": "invalid_scope",
                                     "details": f"scope={body.scope}"})
    accepted, current = CONTEXT.put(body.scope, body.context_id, body.version, body.payload)
    if not accepted:
        return JSONResponse(status_code=409,
                            content={"accepted": False, "reason": "stale_version",
                                     "current_version": current})
    return {"accepted": True,
            "ack_id": f"ack_{body.context_id}_v{body.version}",
            "stored_at": datetime.utcnow().isoformat() + "Z"}


# ----------------------- /v1/tick -----------------------
class TickBody(BaseModel):
    now: str
    available_triggers: list[str] = Field(default_factory=list)


@app.post("/v1/tick")
async def tick(body: TickBody):
    now_iso = body.now
    triggers: list[dict] = []
    for tid in body.available_triggers:
        t = CONTEXT.get("trigger", tid)
        if t:
            # Ensure id key present
            if not t.get("id"):
                t = {**t, "id": tid}
            triggers.append(t)

    chosen = select_actionable(triggers, now_iso, max_actions=20)
    actions: list[dict] = []
    for trg in chosen:
        merchant_id = trg.get("merchant_id") or (trg.get("payload") or {}).get("merchant_id")
        if not merchant_id:
            continue
        merchant = CONTEXT.get("merchant", merchant_id)
        if not merchant:
            continue
        category = CONTEXT.get("category", merchant.get("category_slug", ""))
        customer_id = trg.get("customer_id") or (trg.get("payload") or {}).get("customer_id")
        customer = CONTEXT.get("customer", customer_id) if customer_id else None

        msg = compose(category, merchant, trg, customer, deadline_seconds=18.0)
        if not msg.get("body"):
            continue

        conv_id = f"conv_{merchant_id}_{trg.get('id','')}"
        # New conversation state
        conv = CONVOS.get_or_create(conv_id,
                                    merchant_id=merchant_id,
                                    customer_id=customer_id,
                                    trigger_id=trg.get("id"),
                                    send_as=msg["send_as"])
        conv.last_outbound_body = msg["body"]
        conv.turns.append(ConversationTurn(role="vera" if msg["send_as"] == "vera" else "merchant_on_behalf",
                                           body=msg["body"],
                                           ts=now_iso, cta=msg["cta"]))
        CONVOS.update(conv)
        mark_sent(merchant_id, msg.get("suppression_key", ""), now_iso)

        # Build template params (merchant name + 2 placeholders) for first-out
        merch_name = (merchant.get("identity") or {}).get("name", "")
        actions.append({
            "conversation_id": conv_id,
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "send_as": msg["send_as"],
            "trigger_id": trg.get("id"),
            "template_name": f"vera_{msg['meta']['strategy_kind']}_v1",
            "template_params": [merch_name, msg["meta"]["strategy_kind"], "Vera"],
            "body": msg["body"],
            "cta": msg["cta"],
            "suppression_key": msg.get("suppression_key", ""),
            "rationale": msg["rationale"],
        })
    return {"actions": actions}


# ----------------------- /v1/reply -----------------------
class ReplyBody(BaseModel):
    conversation_id: str
    merchant_id: str | None = None
    customer_id: str | None = None
    from_role: str
    message: str
    received_at: str
    turn_number: int = 1


@app.post("/v1/reply")
async def reply(body: ReplyBody):
    conv = CONVOS.get(body.conversation_id)
    if conv is None:
        # Initialize a state for an unknown conversation (judge starting cold)
        conv = CONVOS.get_or_create(body.conversation_id,
                                    merchant_id=body.merchant_id,
                                    customer_id=body.customer_id,
                                    trigger_id=None,
                                    send_as="vera")

    conv.turns.append(ConversationTurn(role=body.from_role, body=body.message,
                                       ts=body.received_at, cta=None))

    out = respond(conv, body.message, deadline_seconds=18.0)

    if out.get("action") == "send":
        body_out = out.get("body", "")
        conv.last_outbound_body = body_out
        conv.turns.append(ConversationTurn(role="vera" if conv.send_as == "vera" else "merchant_on_behalf",
                                           body=body_out, ts=body.received_at,
                                           cta=out.get("cta")))
    CONVOS.update(conv)
    return out


# Local dev entrypoint
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("bot.main:app", host="0.0.0.0", port=port, reload=False)
