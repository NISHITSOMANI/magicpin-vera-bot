"""Extract grounding facts from contexts. Used both as LLM hints and as a guard whitelist."""
from __future__ import annotations
import re
from typing import Any


def _walk(obj: Any, out: list[str], depth: int = 0) -> None:
    if depth > 6:
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _walk(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, out, depth + 1)
    elif isinstance(obj, (str, int, float)):
        out.append(str(obj))


def collect_strings(*objs: dict | None) -> list[str]:
    out: list[str] = []
    for o in objs:
        if o is not None:
            _walk(o, out)
    return out


_NUM_RE = re.compile(r"(?<![\w/])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?![\w/])")
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_RUPEE_RE = re.compile(r"₹\s*(\d+(?:[,.]\d+)*)")
_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def numeric_anchors(*objs: dict | None) -> set[str]:
    """All numeric-like tokens present in the contexts (whitelist for grounding guard)."""
    anchors: set[str] = set()
    for s in collect_strings(*objs):
        for m in _NUM_RE.finditer(s):
            anchors.add(m.group(1).replace(",", ""))
        for m in _PCT_RE.finditer(s):
            anchors.add(m.group(1))
        for m in _RUPEE_RE.finditer(s):
            anchors.add(m.group(1).replace(",", "").replace(".", ""))
        for m in _DATE_RE.finditer(s):
            anchors.add(m.group(1))
        for m in _YEAR_RE.finditer(s):
            anchors.add(m.group(1))
    # Always-allowed innocuous numbers (small counts, time-of-day)
    for n in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "15", "20", "24", "30", "60", "90"]:
        anchors.add(n)
    return anchors


def named_entities(*objs: dict | None) -> set[str]:
    """Lowercased name-like tokens (>3 chars) present in contexts. Best-effort."""
    out: set[str] = set()
    for s in collect_strings(*objs):
        for tok in re.findall(r"[A-Z][a-zA-Z]{2,}", s):
            out.add(tok.lower())
    return out


def top_anchor_facts(merchant: dict | None, trigger: dict | None, category: dict | None,
                     customer: dict | None = None, k: int = 8) -> list[str]:
    """Human-readable bullets the composer should anchor on. Ranked by signal strength."""
    facts: list[str] = []
    if merchant:
        ident = merchant.get("identity", {}) or {}
        if ident.get("name"):
            facts.append(f"Merchant: {ident['name']} in {ident.get('locality','')}, {ident.get('city','')}")
        if ident.get("owner_first_name"):
            facts.append(f"Owner first name: {ident['owner_first_name']}")
        perf = merchant.get("performance", {}) or {}
        if perf:
            parts = []
            for k_ in ("views", "calls", "directions", "leads", "ctr"):
                if k_ in perf:
                    parts.append(f"{k_}={perf[k_]}")
            if parts:
                facts.append(f"Performance ({perf.get('window_days', 30)}d): " + ", ".join(parts))
            d7 = perf.get("delta_7d") or {}
            if d7:
                facts.append("7d deltas: " + ", ".join(f"{k_}={v}" for k_, v in d7.items()))
        for o in (merchant.get("offers") or [])[:5]:
            facts.append(f"Offer ({o.get('status','?')}): {o.get('title','')}")
        agg = merchant.get("customer_aggregate", {}) or {}
        if agg:
            facts.append("Customers: " + ", ".join(f"{k_}={v}" for k_, v in agg.items()))
        sigs = merchant.get("signals", []) or []
        if sigs:
            facts.append("Signals: " + ", ".join(sigs))
        for rt in (merchant.get("review_themes") or [])[:2]:
            facts.append(f"Review theme: {rt.get('theme')} ({rt.get('sentiment')}, {rt.get('occurrences_30d',0)}/30d)")
    if trigger:
        facts.append(f"Trigger: {trigger.get('kind')} (urgency={trigger.get('urgency')})")
        pl = trigger.get("payload", {}) or {}
        for k_, v in list(pl.items())[:6]:
            facts.append(f"Trigger.{k_}: {v}")
    if category:
        peer = category.get("peer_stats", {}) or {}
        if peer:
            facts.append("Peer stats: " + ", ".join(f"{k_}={v}" for k_, v in peer.items()))
        digest = category.get("digest", []) or []
        if digest:
            top = digest[0]
            facts.append(f"Digest top: {top.get('title','')} — {top.get('source','')}")
    if customer:
        ident = customer.get("identity", {}) or {}
        rel = customer.get("relationship", {}) or {}
        facts.append(f"Customer: {ident.get('name','')} (state={customer.get('state')}, lang={ident.get('language_pref','')})")
        if rel:
            facts.append(f"Relationship: visits={rel.get('visits_total',0)}, last={rel.get('last_visit','')}, services={rel.get('services_received', [])}")
        prefs = customer.get("preferences", {}) or {}
        if prefs:
            facts.append(f"Prefs: {prefs}")
    return facts[:k]
