"""Few-shot case-study examples for composer style transfer."""
from __future__ import annotations

from typing import Any


CASE_STUDIES: list[dict[str, Any]] = [
    {
        "case_study_id": 1,
        "category": "dentists",
        "trigger_kind": "research_digest",
        "send_as": "vera",
        "body": (
            "Dr. Meera, JIDA's Oct issue landed. One item relevant to your high-risk adult "
            "patients: a 2,100-patient trial showed 3-month fluoride recall cuts caries "
            "recurrence 38% better than 6-month. Worth a look (2-min abstract). Want me "
            "to pull it and draft a patient-ed WhatsApp you can share? - JIDA Oct 2026 p.14"
        ),
        "cta": "binary_yes",
        "rationale": (
            "Research digest trigger; anchored on JIDA source, trial size, cohort, and page. "
            "Uses specificity, credibility, and reciprocity."
        ),
        "levers": ["source_citation", "merchant_specific_anchor", "reciprocity", "low_friction_cta"],
    },
    {
        "case_study_id": 2,
        "category": "dentists",
        "trigger_kind": "recall_due",
        "send_as": "merchant_on_behalf",
        "body": (
            "Hi Priya, Dr. Meera's clinic here. It's been 5 months since your last visit; "
            "your 6-month cleaning recall is due. Apke liye 2 slots ready hain: Wed 5 Nov "
            "6pm ya Thu 6 Nov 5pm. Rs.299 cleaning + complimentary fluoride. Reply 1 for "
            "Wed, 2 for Thu, or tell us a time that works."
        ),
        "cta": "slot_choice",
        "rationale": (
            "Recall trigger; uses patient name, elapsed visit window, real slots, price, and "
            "Hindi-English preference."
        ),
        "levers": ["name_personalization", "language_match", "specific_slots", "choice_cta"],
    },
    {
        "case_study_id": 3,
        "category": "salons",
        "trigger_kind": "wedding_package_followup",
        "send_as": "merchant_on_behalf",
        "body": (
            "Hi Kavya, Lakshmi from Studio11 Kapra here. 196 days to your wedding; perfect "
            "window to start the 30-day skin-prep program before serious bridal bookings "
            "roll in. Rs.2,499 covers 4 sessions + a take-home kit. Want me to block your "
            "preferred Saturday 4pm slot for the first session next week?"
        ),
        "cta": "binary_yes",
        "rationale": (
            "Bridal follow-up trigger; ties wedding date, preferred slot, program structure, "
            "and merchant continuity into one ask."
        ),
        "levers": ["relationship_continuity", "date_specificity", "urgency_window", "binary_commit"],
    },
    {
        "case_study_id": 4,
        "category": "salons",
        "trigger_kind": "curious_ask_due",
        "send_as": "vera",
        "body": (
            "Hi Lakshmi! Quick check: what service has been most asked-for this week at "
            "Studio11? I'll turn the answer into a Google post + a 4-line WhatsApp reply "
            "you can use when customers ask about pricing. Takes 5 min."
        ),
        "cta": "open_ended",
        "rationale": (
            "Curious-ask cadence; asks one low-stakes question and externalizes effort into "
            "a ready-to-use artifact."
        ),
        "levers": ["asking_the_merchant", "reciprocity", "effort_externalization"],
    },
    {
        "case_study_id": 5,
        "category": "restaurants",
        "trigger_kind": "ipl_match_today",
        "send_as": "vera",
        "body": (
            "Quick heads-up Suresh: DC vs MI at Arun Jaitley tonight, 7:30pm. Important: "
            "Saturday IPL matches usually shift -12% restaurant covers as people watch at "
            "home. Skip the match-night promo today; push your BOGO pizza as a "
            "delivery-only Saturday special. Want me to draft the Swiggy banner + an Insta "
            "story? Live in 10 min."
        ),
        "cta": "binary_yes",
        "rationale": (
            "IPL trigger; uses match details, contrarian category judgment, existing BOGO "
            "offer, and a time-boxed deliverable."
        ),
        "levers": ["loss_aversion", "operator_judgment", "existing_offer", "time_boxed_cta"],
    },
    {
        "case_study_id": 6,
        "category": "restaurants",
        "trigger_kind": "active_planning_intent",
        "send_as": "vera",
        "body": (
            "Suresh, here's a starter version you can edit: Mylari Corporate Thali for "
            "Indiranagar offices: 10 thalis at Rs.125 each + free delivery; 25 at Rs.115 "
            "+ 2 free filter coffees; 50+ at Rs.105 + 1 free dosa platter. WhatsApp by "
            "5pm the day before; delivery 12:30-1pm. Want me to draft the 3-line outreach?"
        ),
        "cta": "binary_yes",
        "rationale": (
            "Planning intent trigger; provides an editable artifact with tiers, timing, "
            "locality, and a follow-on outreach ask."
        ),
        "levers": ["complete_artifact", "tiered_pricing", "local_specificity", "follow_on_offer"],
    },
    {
        "case_study_id": 7,
        "category": "gyms",
        "trigger_kind": "seasonal_perf_dip",
        "send_as": "vera",
        "body": (
            "Karthik, your views are down 30% this week, but this is the normal April-June "
            "acquisition lull: metro gyms usually see -25 to -35% in this window. Skip ad "
            "spend now; save it for Sept-Oct when conversion is 2x. For now, focus "
            "retention on your 245 members. Want me to draft a summer attendance challenge?"
        ),
        "cta": "binary_yes",
        "rationale": (
            "Seasonal dip trigger; pre-empts anxiety with peer range, exact member count, "
            "and a retention action."
        ),
        "levers": ["anxiety_preemption", "benchmark_range", "retention_reframe", "specific_member_count"],
    },
    {
        "case_study_id": 8,
        "category": "gyms",
        "trigger_kind": "customer_lapsed_hard",
        "send_as": "merchant_on_behalf",
        "body": (
            "Hi Rashmi, Karthik from PowerHouse here. It's been about 8 weeks; happens to "
            "most members at some point, no judgment. We've added a Tue/Thu evening HIIT "
            "class for weight-loss goals (45 min, 6:30pm). Want me to hold a free trial "
            "spot for you next Tue, 30 Apr? Reply YES; no commitment, no auto-charge."
        ),
        "cta": "binary_yes",
        "rationale": (
            "Hard lapse trigger; removes guilt, matches prior goal, names a class, and "
            "offers a low-risk return."
        ),
        "levers": ["no_shame", "goal_match", "specific_class", "barrier_removal"],
    },
    {
        "case_study_id": 9,
        "category": "pharmacies",
        "trigger_kind": "supply_alert",
        "send_as": "vera",
        "body": (
            "Ramesh, urgent: voluntary recall on 2 atorvastatin batches (AT2024-1102, "
            "AT2024-1108) by Mfr Z: sub-potency, no safety risk, but customers should be "
            "informed for replacement. Pulled your repeat-Rx list: 22 chronic-Rx customers "
            "were dispensed these batches in the last 90 days. Want me to draft their "
            "WhatsApp note + replacement-pickup workflow?"
        ),
        "cta": "binary_yes",
        "rationale": (
            "Supply alert trigger; names affected batches, bounded risk, affected customer "
            "count, and an end-to-end workflow."
        ),
        "levers": ["urgency", "batch_specificity", "bounded_risk", "workflow_offer"],
    },
    {
        "case_study_id": 10,
        "category": "pharmacies",
        "trigger_kind": "chronic_refill_due",
        "send_as": "merchant_on_behalf",
        "body": (
            "Namaste, Apollo Health Plus Malviya Nagar yahan. Sharma ji ki 3 monthly "
            "medicines (metformin, atorvastatin, telmisartan) 28 April ko khatam hongi. "
            "Same dose, same brand pack ready hai. Senior discount 15% applied; total "
            "Rs.1,420 (Rs.240 saved). Free home delivery to saved address by 5pm tomorrow. "
            "Reply CONFIRM to dispatch, or call if any dosage changed."
        ),
        "cta": "binary_yes",
        "rationale": (
            "Chronic refill trigger; respectful Hindi-English phrasing with medicine names, "
            "run-out date, savings, delivery, and confirmation path."
        ),
        "levers": ["respectful_salutation", "medicine_specificity", "savings_anchor", "delivery_convenience"],
    },
]


def _extend_unique(out: list[dict[str, Any]], candidates: list[dict[str, Any]], k: int) -> None:
    seen = {item["case_study_id"] for item in out}
    for item in sorted(candidates, key=lambda x: int(x["case_study_id"])):
        if item["case_study_id"] in seen:
            continue
        out.append(item)
        seen.add(item["case_study_id"])
        if len(out) >= k:
            return


def pick_few_shots(category_slug: str, trigger_kind: str, send_as: str, k: int = 2) -> list[dict[str, Any]]:
    """Return deterministic case-study examples, strongest match first."""
    if k <= 0:
        return []
    category = (category_slug or "").strip().lower()
    trigger = (trigger_kind or "").strip()
    sender = (send_as or "").strip()

    selected: list[dict[str, Any]] = []
    _extend_unique(
        selected,
        [
            case
            for case in CASE_STUDIES
            if case["category"] == category
            and case["trigger_kind"] == trigger
            and case["send_as"] == sender
        ],
        k,
    )
    _extend_unique(
        selected,
        [case for case in CASE_STUDIES if case["trigger_kind"] == trigger and case["send_as"] == sender],
        k,
    )
    _extend_unique(selected, [case for case in CASE_STUDIES if case["trigger_kind"] == trigger], k)
    _extend_unique(selected, [case for case in CASE_STUDIES if case["category"] == category], k)
    _extend_unique(selected, CASE_STUDIES, k)
    while len(selected) < k and CASE_STUDIES:
        selected.append(CASE_STUDIES[len(selected) % len(CASE_STUDIES)])
    return selected[:k]
