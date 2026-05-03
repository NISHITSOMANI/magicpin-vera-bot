"""Unit coverage for the four challenge upgrade slices."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bot.composer import critic as critic_mod
from bot.composer.critic import critique_and_revise
from bot.composer.few_shots import pick_few_shots
from bot.composer.guard import check_groundedness_v2
from bot.decision.strategies import for_trigger


def _dentist_contexts() -> tuple[dict, dict, dict, None]:
    category = {
        "slug": "dentists",
        "digest": [
            {
                "title": "3-month fluoride recall vs 6-month",
                "source": "JIDA Oct 2026 p.14",
                "trial_n": 2100,
                "patient_segment": "high-risk adults",
                "result": "38% caries reduction",
            }
        ],
    }
    merchant = {
        "merchant_id": "m_dr_meera",
        "category_slug": "dentists",
        "identity": {"name": "Dr. Meera's Dental Clinic", "owner_first_name": "Dr. Meera"},
        "customer_aggregate": {"high_risk_adult_patients": 124},
    }
    trigger = {
        "id": "trg_jida",
        "kind": "research_digest",
        "urgency": 3,
        "payload": {
            "source": "JIDA Oct 2026 p.14",
            "trial_n": 2100,
            "caries_reduction_percent": 38,
            "patient_segment": "high-risk adults",
        },
    }
    return category, merchant, trigger, None


def test_few_shots_rank_exact_match_first() -> None:
    shots = pick_few_shots("dentists", "research_digest", "vera", k=2)

    assert len(shots) == 2
    assert shots[0]["case_study_id"] == 1
    assert "JIDA" in shots[0]["body"]


def test_critic_revises_weak_and_keeps_strong(monkeypatch: pytest.MonkeyPatch) -> None:
    critic_mod.CRITIC_CACHE.clear()

    def fail_llm(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr(critic_mod, "call_llm", fail_llm)
    category, merchant, trigger, customer = _dentist_contexts()
    strategy = for_trigger(trigger)

    weak_body, weak_cta, weak_scores = critique_and_revise(
        "Hi merchant, want a discount campaign?",
        "binary_yes",
        category,
        merchant,
        trigger,
        customer,
        strategy,
        deadline_seconds=6,
    )
    assert weak_scores["specificity"] <= 4
    assert weak_scores["revised"] is True
    assert weak_body != "Hi merchant, want a discount campaign?"
    assert weak_cta == "binary_yes"

    strong = (
        "Dr. Meera, JIDA's Oct issue landed. One item relevant to your high-risk adult "
        "patients: a 2,100-patient trial showed 3-month fluoride recall cuts caries "
        "recurrence 38% better than 6-month. Want me to pull it and draft a patient-ed "
        "WhatsApp you can share? - JIDA Oct 2026 p.14"
    )
    final_body, final_cta, strong_scores = critique_and_revise(
        strong,
        "binary_yes",
        category,
        merchant,
        trigger,
        customer,
        strategy,
        deadline_seconds=6,
    )
    assert final_body == strong
    assert final_cta == "binary_yes"
    assert all(strong_scores[key] >= 9 for key in (
        "specificity",
        "category_fit",
        "merchant_fit",
        "trigger_relevance",
        "engagement_compulsion",
    ))
    assert strong_scores["revised"] is False


def test_fact_lineage_grounding() -> None:
    category, merchant, trigger, customer = _dentist_contexts()
    contexts = {"category": category, "merchant": merchant, "trigger": trigger, "customer": customer}

    grounded, unsourced, traced = check_groundedness_v2(
        "JIDA Oct 2026 p.14 found 38% caries reduction in 2,100 patients",
        contexts,
    )
    assert grounded is True
    assert not any(claim.kind in {"percent", "source_citation"} for claim in unsourced)
    assert traced

    grounded, unsourced, _traced = check_groundedness_v2("Lancet 2025 found a better protocol", contexts)
    assert grounded is False
    assert any(claim.kind == "source_citation" and "Lancet" in claim.text for claim in unsourced)

    grounded, unsourced, _traced = check_groundedness_v2("Want me to draft 3 posts in 5 min?", contexts)
    assert grounded is True
    assert unsourced == []


def test_diagnostics_tracks_contexts_actions_and_closed_replies(monkeypatch: pytest.MonkeyPatch) -> None:
    import bot.main as main
    from bot.store import CONTEXT, CONVOS, COMPOSE_CACHE, MERCHANT_AUTO_STRIKES, SENT_SUPPRESSION_KEYS

    CONTEXT._data.clear()
    CONVOS._data.clear()
    COMPOSE_CACHE.clear()
    MERCHANT_AUTO_STRIKES.clear()
    SENT_SUPPRESSION_KEYS.clear()
    main.LAST_TICK_AT = None
    main.LAST_REPLY_AT = None
    main.MESSAGES_SENT = 0

    def fake_compose(category, merchant, trigger, customer=None, *, deadline_seconds=22.0):
        return {
            "body": "Suresh, want me to draft the BOGO post now?",
            "cta": "binary_yes",
            "send_as": "vera",
            "suppression_key": trigger.get("suppression_key", ""),
            "rationale": "test",
            "meta": {"strategy_kind": "curious_ask_due"},
        }

    def fake_respond(conv, inbound, *, deadline_seconds=22.0):
        if "stop" in inbound:
            conv.state = "closed"
            return {"action": "end", "rationale": "closed"}
        return {"action": "send", "body": "Done, sending.", "cta": "info_only", "rationale": "test"}

    monkeypatch.setattr(main, "compose", fake_compose)
    monkeypatch.setattr(main, "respond", fake_respond)

    with TestClient(main.app) as client:
        for idx in range(5):
            res = client.post(
                "/v1/context",
                json={
                    "scope": "category",
                    "context_id": f"cat_{idx}",
                    "version": 1,
                    "payload": {"slug": f"cat_{idx}"},
                },
            )
            assert res.status_code == 200

        client.post(
            "/v1/context",
            json={
                "scope": "merchant",
                "context_id": "m_1",
                "version": 1,
                "payload": {"merchant_id": "m_1", "category_slug": "cat_0", "identity": {"name": "SK Pizza"}},
            },
        )
        client.post(
            "/v1/context",
            json={
                "scope": "trigger",
                "context_id": "trg_1",
                "version": 1,
                "payload": {
                    "id": "trg_1",
                    "kind": "curious_ask_due",
                    "merchant_id": "m_1",
                    "urgency": 5,
                    "suppression_key": "sk_1",
                },
            },
        )

        diag = client.get("/v1/diagnostics").json()
        assert diag["contexts_loaded"]["category"] == 5

        tick = client.post("/v1/tick", json={"now": "2026-05-03T00:00:00Z", "available_triggers": ["trg_1"]})
        assert len(tick.json()["actions"]) == 1
        assert client.get("/v1/diagnostics").json()["messages_sent_total"] == 1

        for msg in ("yes", "ok", "stop messaging"):
            client.post(
                "/v1/reply",
                json={
                    "conversation_id": "conv_m_1_trg_1",
                    "merchant_id": "m_1",
                    "from_role": "merchant",
                    "message": msg,
                    "received_at": "2026-05-03T00:01:00Z",
                },
            )

        diag = client.get("/v1/diagnostics").json()
        assert diag["conversations_closed"] == 1
        assert diag["last_tick_at"] is not None
        assert diag["last_reply_at"] is not None
