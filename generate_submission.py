"""Generate submission.jsonl by running compose() over the 30 canonical test pairs."""
from __future__ import annotations
import json, os, sys, pathlib
from dotenv import load_dotenv
load_dotenv()

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))

from bot.compose import compose

EXP = ROOT / "expanded"


def load_json(p: pathlib.Path) -> dict:
    return json.loads(p.read_text())


def find_merchant(mid: str) -> dict | None:
    for f in (EXP / "merchants").glob("*.json"):
        if mid in f.stem:
            return load_json(f)
    return None


def find_customer(cid: str | None) -> dict | None:
    if not cid:
        return None
    for f in (EXP / "customers").glob("*.json"):
        if cid in f.stem:
            return load_json(f)
    return None


def find_trigger(tid: str) -> dict | None:
    for f in (EXP / "triggers").glob("*.json"):
        if tid in f.stem:
            return load_json(f)
    return None


def main():
    import time as _t
    pairs = load_json(EXP / "test_pairs.json")["pairs"]
    out_path = ROOT / "submission.jsonl"
    with out_path.open("w") as fh:
        for i, pair in enumerate(pairs):
            if i > 0:
                _t.sleep(4.5)  # ~13 RPM, safely under Gemini Flash 15 RPM free tier
            merchant = find_merchant(pair["merchant_id"])
            trigger = find_trigger(pair["trigger_id"])
            customer = find_customer(pair.get("customer_id"))
            if not merchant or not trigger:
                print(f"SKIP {pair['test_id']}: merchant or trigger not found", file=sys.stderr)
                continue
            cat_slug = merchant.get("category_slug")
            category = load_json(EXP / "categories" / f"{cat_slug}.json") if cat_slug else None
            msg = compose(category, merchant, trigger, customer, deadline_seconds=20.0)
            line = {
                "test_id": pair["test_id"],
                "body": msg["body"],
                "cta": msg["cta"],
                "send_as": msg["send_as"],
                "suppression_key": msg["suppression_key"],
                "rationale": msg["rationale"],
            }
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
            print(f"{pair['test_id']}  [{msg['meta']['provider']:10}]  {msg['body'][:90]}...")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
