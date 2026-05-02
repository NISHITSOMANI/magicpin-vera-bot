"""Trigger-kind → strategy map. Each strategy = levers + CTA shape + framing rules."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Strategy:
    kind: str
    levers: list[str]
    cta_shape: str  # "binary_yes_stop" | "open_ended" | "binary_yes" | "info_only" | "slot_choice"
    framing: str
    send_as: str = "vera"  # default; overridden when scope=customer
    must_anchor: list[str] = None  # facts that should ground the message
    voice_override: str | None = None
    max_chars: int = 480


STRATEGIES: dict[str, Strategy] = {
    "research_digest": Strategy(
        kind="research_digest",
        levers=["specificity", "reciprocity", "curiosity"],
        cta_shape="binary_yes",
        framing="Cite the digest source + page; tie to a specific merchant cohort signal; offer to draft follow-up artifact.",
        must_anchor=["digest.source", "digest.title", "merchant.signals"],
    ),
    "regulation_change": Strategy(
        kind="regulation_change",
        levers=["specificity", "loss_aversion", "reciprocity"],
        cta_shape="binary_yes",
        framing="Name the regulator + clause + effective date; offer compliance checklist.",
    ),
    "compliance_dci_radiograph": Strategy(
        kind="regulation_change",
        levers=["specificity", "loss_aversion"],
        cta_shape="binary_yes",
        framing="Cite the DCI clause + effective date; offer 1-pager checklist.",
    ),
    "cde_opportunity": Strategy(
        kind="cde_opportunity",
        levers=["specificity", "curiosity"],
        cta_shape="binary_yes",
        framing="Webinar/CDE date + topic + credit hours; one-line value prop.",
    ),
    "perf_dip": Strategy(
        kind="perf_dip",
        levers=["specificity", "reciprocity", "asking_the_merchant"],
        cta_shape="binary_yes",
        framing="Quote exact metric drop, propose ONE specific recovery action tied to active offers.",
    ),
    "perf_spike": Strategy(
        kind="perf_spike",
        levers=["social_proof", "curiosity", "asking_the_merchant"],
        cta_shape="open_ended",
        framing="Celebrate with the actual number; ask which channel drove it; offer to amplify.",
    ),
    "seasonal_perf_dip": Strategy(
        kind="seasonal_perf_dip",
        levers=["specificity", "reciprocity"],
        cta_shape="binary_yes",
        framing="Reframe seasonal — name month range + peer benchmark — propose retention move not panic.",
    ),
    "milestone_reached": Strategy(
        kind="milestone_reached",
        levers=["social_proof", "reciprocity"],
        cta_shape="binary_yes",
        framing="Name the milestone number; tie to a leverage move (Google post, review request).",
    ),
    "competitor_opened": Strategy(
        kind="competitor_opened",
        levers=["loss_aversion", "specificity"],
        cta_shape="binary_yes",
        framing="State distance + competitor name; one defensive move (review push or differentiator highlight).",
    ),
    "review_theme_emerged": Strategy(
        kind="review_theme_emerged",
        levers=["specificity", "reciprocity"],
        cta_shape="binary_yes",
        framing="Quote theme + count; offer drafted public response template.",
    ),
    "ipl_match_today": Strategy(
        kind="ipl_match_today",
        levers=["specificity", "loss_aversion"],
        cta_shape="binary_yes",
        framing="Match details + counter-intuitive insight (e.g., Sat IPL = -12% covers); leverage existing offer.",
    ),
    "festival_upcoming": Strategy(
        kind="festival_upcoming",
        levers=["specificity", "reciprocity"],
        cta_shape="binary_yes",
        framing="Days-to-festival + category-fit motif; one drafted artifact (post/banner/promo).",
    ),
    "active_planning_intent": Strategy(
        kind="active_planning_intent",
        levers=["effort_externalization", "specificity"],
        cta_shape="binary_yes",
        framing="Continue the plan — provide a complete editable starter draft with prices/tiers.",
    ),
    "curious_ask_due": Strategy(
        kind="curious_ask_due",
        levers=["asking_the_merchant", "reciprocity"],
        cta_shape="open_ended",
        framing="Low-stakes question; promise to convert answer into a 5-min artifact.",
        max_chars=320,
    ),
    "dormant_with_vera": Strategy(
        kind="dormant_with_vera",
        levers=["curiosity", "asking_the_merchant"],
        cta_shape="open_ended",
        framing="Acknowledge gap; lead with a specific local/category fact; light question.",
        max_chars=320,
    ),
    "renewal_due": Strategy(
        kind="renewal_due",
        levers=["specificity", "loss_aversion"],
        cta_shape="binary_yes",
        framing="Days-to-expiry + concrete realized value (calls/leads from period); single renewal CTA.",
    ),
    "gbp_unverified": Strategy(
        kind="gbp_unverified",
        levers=["effort_externalization", "specificity"],
        cta_shape="binary_yes",
        framing="Name what's missing exactly; 5-min effort frame.",
    ),
    "winback_eligible": Strategy(
        kind="winback_eligible",
        levers=["specificity", "reciprocity"],
        cta_shape="binary_yes",
        framing="Name dormant duration + a re-engagement artifact draft.",
    ),
    "supply_alert": Strategy(
        kind="supply_alert",
        levers=["specificity", "loss_aversion"],
        cta_shape="binary_yes",
        framing="Name SKU + batch + action window; one safety/regulatory step.",
    ),
    "category_seasonal": Strategy(
        kind="category_seasonal",
        levers=["specificity", "asking_the_merchant"],
        cta_shape="binary_yes",
        framing="Name season window + demand shift fact; propose one stocking/staffing move.",
    ),

    # Customer-facing
    "recall_due": Strategy(
        kind="recall_due",
        levers=["specificity", "reciprocity"],
        cta_shape="slot_choice",
        framing="Address customer by name; reference last visit date; offer 1-2 real slots + price.",
        send_as="merchant_on_behalf",
    ),
    "appointment_tomorrow": Strategy(
        kind="appointment_tomorrow",
        levers=["specificity"],
        cta_shape="binary_yes",
        framing="Confirm time/date + brief prep tip; one binary confirm CTA.",
        send_as="merchant_on_behalf",
        max_chars=260,
    ),
    "chronic_refill_due": Strategy(
        kind="chronic_refill_due",
        levers=["specificity", "reciprocity"],
        cta_shape="binary_yes",
        framing="Name medication name window; offer refill + delivery.",
        send_as="merchant_on_behalf",
    ),
    "trial_followup": Strategy(
        kind="trial_followup",
        levers=["specificity", "reciprocity"],
        cta_shape="binary_yes",
        framing="Reference the trial; offer next-step package with price.",
        send_as="merchant_on_behalf",
    ),
    "wedding_package_followup": Strategy(
        kind="wedding_package_followup",
        levers=["specificity", "reciprocity"],
        cta_shape="binary_yes",
        framing="Days-to-wedding + program structure + slot suggestion.",
        send_as="merchant_on_behalf",
    ),
    "customer_lapsed_soft": Strategy(
        kind="customer_lapsed_soft",
        levers=["specificity", "reciprocity"],
        cta_shape="binary_yes",
        framing="Name months since last visit; concrete returning-customer offer.",
        send_as="merchant_on_behalf",
    ),
    "customer_lapsed_hard": Strategy(
        kind="customer_lapsed_hard",
        levers=["curiosity", "reciprocity"],
        cta_shape="binary_yes",
        framing="Light win-back tone; one specific reason to come back.",
        send_as="merchant_on_behalf",
    ),
}


DEFAULT_STRATEGY = Strategy(
    kind="generic",
    levers=["specificity", "reciprocity"],
    cta_shape="binary_yes",
    framing="Use one verifiable fact from contexts; one binary CTA.",
)


def for_trigger(trigger: dict | None) -> Strategy:
    if not trigger:
        return DEFAULT_STRATEGY
    s = STRATEGIES.get(trigger.get("kind", ""), DEFAULT_STRATEGY)
    # Customer scope override
    if trigger.get("scope") == "customer" and s.send_as == "vera":
        s = Strategy(
            kind=s.kind, levers=s.levers, cta_shape=s.cta_shape, framing=s.framing,
            send_as="merchant_on_behalf", must_anchor=s.must_anchor,
            voice_override=s.voice_override, max_chars=s.max_chars,
        )
    return s
