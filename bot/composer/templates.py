"""Deterministic template fallbacks per trigger kind. Used when LLM fails or is ungrounded.

Each template grounds in real fields from the contexts — no hallucinated data.
"""
from __future__ import annotations
from ..decision.voice import language_for


def _name(merchant: dict | None) -> str:
    if not merchant:
        return "there"
    ident = merchant.get("identity", {}) or {}
    return ident.get("owner_first_name") or ident.get("name", "there")


def _biz(merchant: dict | None) -> str:
    return ((merchant or {}).get("identity", {}) or {}).get("name", "your business")


def _cat_slug(merchant: dict | None, category: dict | None) -> str:
    if category and category.get("slug"):
        return category["slug"]
    return (merchant or {}).get("category_slug", "")


def _is_dentist(merchant: dict | None, category: dict | None) -> bool:
    return _cat_slug(merchant, category) == "dentists"


def _active_offer_title(merchant: dict | None) -> str | None:
    for o in (merchant.get("offers") or []) if merchant else []:
        if o.get("status") == "active" and o.get("title"):
            return o["title"]
    return None


def _digest_top(category: dict | None) -> dict:
    if not category:
        return {}
    d = (category.get("digest") or [])
    return d[0] if d else {}


def _greet(merchant: dict | None, category: dict | None) -> str:
    name = _name(merchant)
    if _is_dentist(merchant, category):
        return f"Dr. {name}"
    return name


def _pct(v) -> str:
    if v is None:
        return ""
    try:
        n = float(v)
        sign = "+" if n >= 0 else ""
        return f"{sign}{int(n*100)}%"
    except Exception:
        return str(v)


def render(category: dict | None, merchant: dict | None, trigger: dict | None,
           customer: dict | None) -> tuple[str, str]:
    """Return (body, cta) — minimal grounded fallback."""
    kind = (trigger or {}).get("kind", "generic")
    payload = (trigger or {}).get("payload", {}) or {}
    name = _name(merchant)
    greet = _greet(merchant, category)
    biz = _biz(merchant)
    perf = (merchant or {}).get("performance", {}) or {}
    offer = _active_offer_title(merchant)

    if kind == "research_digest":
        d = _digest_top(category)
        if d.get("title"):
            extra = ""
            agg = (merchant or {}).get("customer_aggregate", {}) or {}
            if "high_risk_adult_count" in agg:
                extra = f" Relevant for your {agg['high_risk_adult_count']} high-risk adult patients — "
            return (f"{greet}, new in your category: {d.get('title')} ({d.get('source','')}).{extra}"
                    f"Want me to pull a 2-min abstract + draft a patient-share WhatsApp?"), "binary_yes"
        return (f"{greet}, fresh research relevant to your patient mix landed this week. "
                f"Want me to pull the abstract for you?"), "binary_yes"

    if kind == "cde_opportunity":
        d = _digest_top(category)
        credits = payload.get("credits")
        fee = payload.get("fee", "")
        title = d.get("title") or "CDE webinar"
        src = d.get("source", "")
        extra = ""
        if credits:
            extra = f" {credits} CDE credits"
        if fee:
            extra += f", {fee.replace('_',' ')}" if extra else f" {fee.replace('_',' ')}"
        return (f"{greet}, CDE alert: {title}{f' ({src})' if src else ''}.{extra}. "
                f"Want me to share the registration link?"), "binary_yes"

    if kind in ("regulation_change", "compliance_dci_radiograph"):
        d = _digest_top(category)
        title = d.get("title") or payload.get("title", "regulation update")
        src = d.get("source") or payload.get("source", "")
        return (f"{greet}, regulation update: {title}{f' — {src}' if src else ''}. "
                f"Want me to share a 1-page compliance checklist for your clinic?"), "binary_yes"

    if kind == "perf_dip":
        metric = payload.get("metric", "calls")
        delta = payload.get("delta_pct")
        window = payload.get("window", "7d")
        if delta is not None:
            return (f"{name}, your {metric} are {_pct(delta)} this {window}. "
                    f"One quick lever — push your {offer or 'active offer'} via a Google post + "
                    f"WhatsApp template today. Want me to draft both?"), "binary_yes"
        d7 = perf.get("delta_7d", {}) or {}
        v = d7.get("calls_pct") or d7.get("views_pct")
        if v is not None:
            return (f"{name}, week-on-week {_pct(v)} on calls/views. "
                    f"Push your {offer or 'active offer'} via a Google post — want me to draft it?"), "binary_yes"
        return (f"{name}, your week numbers slipped. Want me to draft a Google post around "
                f"{offer or 'your active offer'} to recover this week?"), "binary_yes"

    if kind == "perf_spike":
        metric = payload.get("metric", "")
        delta = payload.get("delta_pct")
        if delta is not None:
            return (f"{name}, {metric or 'traffic'} is {_pct(delta)} this week — strong signal. "
                    f"Which channel drove it? I'll amplify it for the rest of the month."), "open_ended"
        d7 = perf.get("delta_7d", {}) or {}
        v = d7.get("views_pct") or d7.get("calls_pct")
        if v is not None:
            return (f"{name}, views are {_pct(v)} this week — strong signal. "
                    f"Which channel drove it? I can amplify it."), "open_ended"
        return (f"{name}, traffic looks strong this week. Which channel drove it? "
                f"I'll amplify the rest of the month."), "open_ended"

    if kind == "seasonal_perf_dip":
        return (f"{name}, this dip is the expected April-June seasonal — peers in your category "
                f"see the same pattern. Want me to draft a retention nudge to your active members "
                f"instead of an acquisition push?"), "binary_yes"

    if kind == "milestone_reached":
        metric = payload.get("metric", "milestone")
        value_now = payload.get("value_now")
        milestone = payload.get("milestone_value") or payload.get("value_now")
        if value_now and milestone:
            return (f"{name}, you're at {value_now} {metric} — {milestone - value_now if isinstance(milestone, int) and isinstance(value_now, int) else ''} away from {milestone}. "
                    f"Want me to draft a Google post + thank-you WhatsApp to your last 20 customers to push you over?"), "binary_yes"
        return (f"{name}, milestone moment incoming. Want me to draft a Google post + a "
                f"thank-you template you can send to recent customers?"), "binary_yes"

    if kind == "competitor_opened":
        comp = payload.get("competitor_name") or "a new competitor"
        dist = payload.get("distance_km")
        their_offer = payload.get("their_offer")
        opened = payload.get("opened_date", "")
        d_str = f"{dist} km away" if dist is not None else "nearby"
        offer_line = f" Their hook: {their_offer}." if their_offer else ""
        return (f"{name}, heads-up: {comp} opened {d_str}{f' ({opened})' if opened else ''}.{offer_line} "
                f"One defensive move — push a fresh review request to your last 20 happy customers "
                f"this week. Want me to draft the WhatsApp?"), "binary_yes"

    if kind == "review_theme_emerged":
        theme = payload.get("theme", "a recurring theme")
        occ = payload.get("occurrences_30d")
        trend = payload.get("trend", "")
        quote = payload.get("common_quote", "")
        bits = []
        if occ:
            bits.append(f"{occ} mentions in 30d")
        if trend:
            bits.append(trend)
        meta = f" ({', '.join(bits)})" if bits else ""
        q = f' Quote: "{quote}".' if quote else ""
        return (f"{name}, review theme emerging: {theme}{meta}.{q} "
                f"Want me to draft a public response template + a private fix note?"), "binary_yes"

    if kind == "ipl_match_today":
        match = payload.get("match", "tonight's IPL match")
        venue = payload.get("venue", "")
        is_weeknight = payload.get("is_weeknight", True)
        weekend_note = " (Saturday matches usually shift covers to delivery)" if not is_weeknight else ""
        v = f" at {venue}" if venue else ""
        return (f"{name}, {match}{v} today.{weekend_note} Want me to draft a quick match-night "
                f"promo around your {offer or 'active offer'} — Swiggy banner + Insta story, live in 10 min?"), "binary_yes"

    if kind == "festival_upcoming":
        fest = payload.get("festival", "festival")
        days = payload.get("days_until", payload.get("days_to"))
        d_str = f" in {days} days" if days else ""
        return (f"{name}, {fest}{d_str}. Want me to draft a category-fit promo + Google post "
                f"you can review in 2 minutes?"), "binary_yes"

    if kind == "active_planning_intent":
        topic = payload.get("intent_topic", "the package we discussed").replace("_", " ")
        return (f"{name}, here's a starter draft for {topic} — you can edit. "
                f"Want me to share the structure now?"), "binary_yes"

    if kind == "curious_ask_due":
        return (f"Hi {name}! Quick check — what service has been most asked-for this week? "
                f"I'll turn the answer into a Google post + a 4-line WhatsApp reply you can use. 5 min."), "open_ended"

    if kind == "dormant_with_vera":
        return (f"Hi {name}, been a bit since we caught up. One quick question: what's the #1 thing "
                f"you'd want me to fix on your Google profile this week?"), "open_ended"

    if kind == "renewal_due":
        sub = (merchant or {}).get("subscription", {}) or {}
        days = sub.get("days_remaining", "")
        d_str = f" in {days} days" if days != "" else ""
        leads = perf.get("leads")
        calls = perf.get("calls")
        proof = ""
        if leads or calls:
            parts = []
            if calls:
                parts.append(f"{calls} calls")
            if leads:
                parts.append(f"{leads} leads")
            proof = f" Last 30d: {', '.join(parts)}."
        return (f"{name}, your magicpin Pro renewal is due{d_str}.{proof} "
                f"Want me to share a 1-line summary before you decide?"), "binary_yes"

    if kind == "gbp_unverified":
        path = payload.get("verification_path", "verification").replace("_or_", " or ").replace("_", " ")
        uplift = payload.get("estimated_uplift_pct")
        u = f" Verified profiles see ~{int(float(uplift)*100)}% more views." if uplift else ""
        return (f"{name}, your Google profile is unverified — fastest fix is via {path}.{u} "
                f"Want me to walk you through the 5-min steps?"), "binary_yes"

    if kind == "supply_alert":
        mol = payload.get("molecule", "an SKU")
        batches = payload.get("affected_batches") or []
        mfr = payload.get("manufacturer", "")
        b_str = f" Batches: {', '.join(batches)}" if batches else ""
        m_str = f" ({mfr})" if mfr else ""
        return (f"{name}, supply alert: {mol}{m_str}.{b_str}. "
                f"Want me to draft a customer-facing recall notice you can WhatsApp to recent buyers?"), "binary_yes"

    if kind == "category_seasonal":
        season = payload.get("season", "the season").replace("_", " ")
        trends = payload.get("trends") or []
        t_str = ""
        if trends:
            top = ", ".join(t.replace("_demand_", " ").replace("+", "+").replace("-", "−") for t in trends[:3])
            t_str = f" Demand shifts: {top}."
        return (f"{name}, {season} demand is shifting.{t_str} "
                f"Want me to flag a 3-SKU shelf-front change for this week?"), "binary_yes"

    if kind == "winback_eligible":
        cust_name = (customer or {}).get("identity", {}).get("name", name)
        return (f"Hi {cust_name}, it's been a while. We've kept {offer or 'a fresh offer'} ready for you this week. "
                f"Want a slot?"), "binary_yes"

    # Customer-facing
    if kind == "recall_due":
        cust_name = (customer or {}).get("identity", {}).get("name", "")
        rel = (customer or {}).get("relationship", {}) or {}
        last = rel.get("last_visit", "")
        b = _biz(merchant)
        last_str = f" since {last}" if last else ""
        offer_str = f" {offer}." if offer else ""
        return (f"Hi {cust_name}, {b} here. It's been a while{last_str} — your recall window is open.{offer_str} "
                f"Want us to confirm a slot this week?"), "binary_yes"

    if kind == "appointment_tomorrow":
        cust_name = (customer or {}).get("identity", {}).get("name", "")
        slot = payload.get("slot", payload.get("time", "tomorrow"))
        return (f"Hi {cust_name}, just confirming your appointment {slot}. "
                f"Reply YES to confirm or share a better time."), "binary_yes_stop"

    if kind == "chronic_refill_due":
        cust_name = (customer or {}).get("identity", {}).get("name", "")
        med = payload.get("medication") or payload.get("sku") or "your monthly refill"
        return (f"Hi {cust_name}, {med} refill window is open. "
                f"Want us to deliver this week — same address?"), "binary_yes"

    if kind == "trial_followup":
        cust_name = (customer or {}).get("identity", {}).get("name", "")
        return (f"Hi {cust_name}, hope the trial went well. Want to lock in the full package — "
                f"I can send 2 slot options this week?"), "binary_yes"

    if kind == "wedding_package_followup":
        cust_name = (customer or {}).get("identity", {}).get("name", "")
        days = payload.get("days_to_wedding")
        d = f" {days} days to your wedding —" if days else ""
        return (f"Hi {cust_name},{d} perfect window to start the prep program. "
                f"Want me to block your preferred slot for the first session next week?"), "binary_yes"

    if kind in ("customer_lapsed_soft", "customer_lapsed_hard"):
        cust_name = (customer or {}).get("identity", {}).get("name", "")
        return (f"Hi {cust_name}, it's been a while since your last visit. "
                f"We've got {offer or 'a returning-customer slot'} ready this week. Want to book?"), "binary_yes"

    # Generic fallback
    if offer:
        return (f"{name}, quick one — your {offer} is live. "
                f"Want me to push it via a Google post + WhatsApp template this week?"), "binary_yes"
    return (f"{name}, quick check on your listing this week. "
            f"Want me to share the top 1 fix that would lift calls?"), "binary_yes"
