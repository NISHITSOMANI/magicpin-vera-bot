"""Interactive REPL for chatting with your local bot.

Usage:
  1. Start the bot in another terminal:  python -m bot.main
  2. Run this:                           python chat.py
  3. Type messages; type "quit" to exit.
"""
from __future__ import annotations
import json, sys, os, pathlib, uuid
import httpx

BOT_URL = os.environ.get("BOT_URL", "http://localhost:8080")
ROOT = pathlib.Path(__file__).parent
EXP = ROOT / "expanded"


def load_json(p: pathlib.Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def push_context(scope: str, context_id: str, payload: dict) -> None:
    body = {
        "scope": scope,
        "context_id": context_id,
        "version": 1,
        "payload": payload,
        "delivered_at": "2026-05-03T10:00:00Z",
    }
    r = httpx.post(f"{BOT_URL}/v1/context", json=body, timeout=20)
    print(f"  push {scope}/{context_id} → {r.status_code} {r.json().get('accepted')}")


def main():
    print(f"Vera local chat — bot at {BOT_URL}")
    if not EXP.exists():
        print("ERROR: run 'python dataset/generate_dataset.py --seed-dir dataset --out expanded' first")
        sys.exit(1)

    # Push all categories
    print("\nLoading contexts...")
    for f in (EXP / "categories").glob("*.json"):
        d = load_json(f)
        push_context("category", d["slug"], d)

    # Pick a merchant
    merchants = sorted((EXP / "merchants").glob("*.json"))
    print("\nAvailable merchants:")
    for i, f in enumerate(merchants[:10]):
        d = load_json(f)
        print(f"  [{i}] {d['merchant_id']:50}  ({d.get('category_slug','')})")
    pick = input("Pick merchant index [0]: ").strip() or "0"
    merchant = load_json(merchants[int(pick)])
    push_context("merchant", merchant["merchant_id"], merchant)

    # Optional: pick a trigger for context
    triggers = sorted((EXP / "triggers").glob("*.json"))
    matching = [t for t in triggers if (load_json(t).get("merchant_id") == merchant["merchant_id"])]
    if matching:
        print("\nMerchant has triggers (optional, useful for grounding the conversation):")
        for i, f in enumerate(matching[:10]):
            d = load_json(f)
            print(f"  [{i}] {d['id']:50}  ({d.get('kind')})")
        print(f"  [s] skip")
        pick = input("Pick trigger index or s [s]: ").strip() or "s"
        trigger_id = None
        if pick != "s":
            trig = load_json(matching[int(pick)])
            push_context("trigger", trig["id"], trig)
            trigger_id = trig["id"]
    else:
        trigger_id = None

    conv_id = f"conv_local_{uuid.uuid4().hex[:8]}"
    print(f"\nConversation: {conv_id}\nType your message as the merchant. Type 'quit' to exit.\n")

    turn = 1
    while True:
        msg = input("merchant> ").strip()
        if not msg or msg.lower() in ("quit", "exit", "q"):
            break
        body = {
            "conversation_id": conv_id,
            "merchant_id": merchant["merchant_id"],
            "customer_id": None,
            "from_role": "merchant",
            "message": msg,
            "received_at": "2026-05-03T10:00:00Z",
            "turn_number": turn,
        }
        try:
            r = httpx.post(f"{BOT_URL}/v1/reply", json=body, timeout=30)
            data = r.json()
        except Exception as e:
            print(f"  ERROR: {e}")
            continue
        action = data.get("action", "?")
        if action == "send":
            print(f"vera>     {data.get('body','')}")
            print(f"          (cta={data.get('cta','')})")
        elif action == "wait":
            print(f"vera>     [waiting {data.get('wait_seconds')}s]  {data.get('rationale','')}")
        elif action == "end":
            print(f"vera>     [conversation ended]  {data.get('rationale','')}")
            break
        turn += 1

    print("\nBye.")


if __name__ == "__main__":
    main()
