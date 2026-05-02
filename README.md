---
title: Vera Bot
emoji: 💬
colorFrom: indigo
colorTo: pink
sdk: docker
app_port: 7860
pinned: false
short_description: Vera — magicpin merchant-AI message engine
---

# Vera Bot — magicpin AI Challenge

**Author**: Nishit Somani · `somaninishit36@gmail.com`

A deterministic, grounded WhatsApp message engine for merchant growth. Compose `(category, merchant, trigger, customer?)` → next message + CTA + send_as + suppression key + rationale.

## Approach

A typical submission stuffs all 4 contexts into one LLM prompt and ships the result. That ceilings around 30/50 because it hallucinates, repeats itself, ignores cooldowns, and breaks under the post-submission context twist. This bot is built as a **system**, not a prompt:

```
HTTP (FastAPI · 5 endpoints)
   │
Context Store  (in-mem · idempotent on (scope, id, version))
   │
Decision Engine  (pure Python — no LLM)
   │   • Trigger router: 25+ kinds → strategy (levers + CTA shape + max length + send_as)
   │   • Voice profile: clinical / warm-practical / operator / energetic / utility
   │   • Language detector: en | hi-en (per merchant.identity.languages or customer.language_pref)
   │   • Cooldown: per-merchant min hours by urgency; suppression-key memory
   │   • Specificity ranker: fact bundle (numbers > dates > named entities > peer stats)
   │
Composer  (Gemini 2.5 Flash → Groq Llama 3.3 70B → OpenRouter DeepSeek/Llama free)
   │   • Strict JSON output, temperature=0
   │   • System prompt enforces voice + grounding + single CTA
   │   • Few-shot strategy framing per trigger
   │
Grounding Guard  (post-LLM, pure Python)
   │   • Whitelist every numeric/date token from contexts
   │   • Reject unknown numbers; ignore tiny counts (≤99)
   │   • Voice-taboo vocab check (e.g., "guaranteed" for dentists)
   │   • One repair pass on violation; template fallback if still bad
   │
Conversation FSM  (for /v1/reply)
       • Auto-reply detection (verbatim hash + canned-phrase patterns; cross-conversation per merchant)
       • Intent transition: regex + actioning-words guard → hard-routes to "Done — drafting now"
       • Hostile / not-interested → end immediately
       • Off-topic → 1 polite redirect, then end
       • Anti-repetition: never re-emit a prior outbound body verbatim
```

The same `compose()` is the pure function used by `/v1/tick`, `/v1/reply` follow-ups, and the offline `submission.jsonl` generator — judge twist scenarios with new contexts adapt automatically.

## Why this design

1. **Hallucination shield**: every number, ₹ amount, date, source citation in the LLM output is regex-extracted and verified against an "allowed-facts" whitelist built from the 4 contexts. Failed facts trigger a single repair pass; if the repair still fails, a deterministic template (also grounded) ships. Eliminates the #1 score-killer.

2. **Restraint as strategy**: many bots will spam every tick. Per-merchant cooldown (≥4–24h depending on urgency) plus suppression-key memory means we send less but score more.

3. **Determinism by construction**: `temperature=0`, sorted JSON keys, normalized whitespace, content-hashed compose cache keyed on `(category, merchant, trigger, customer)` versions. Re-running the same input returns byte-identical output.

4. **Zero-cost free-tier stack**: Gemini 2.5 Flash (primary) → Groq Llama 3.3 70B → OpenRouter DeepSeek/Llama free. Provider router transparently fails over on rate limits; deterministic templates as final fallback ensure the bot never returns empty bodies.

5. **Replay-test ready**: the FSM passes the official `judge_simulator.py` for warmup, auto-reply detection, intent transition, and hostile handling out of the box.

## Tradeoffs

- **Cost vs. quality**: Sticking to free-tier models. Quality preserved by stronger deterministic scaffolding (grounding guard + per-trigger templates) so free models with our system ≥ paid models without it.
- **In-memory state vs. persistence**: Test brief explicitly allows in-memory; we don't restart between calls. Simpler, faster, no DB.
- **Strict guard vs. richer prose**: Numeric grounding sometimes rejects creative LLM phrasing; we accept the tradeoff because hallucinated facts score lower than a slightly drier-but-real body.

## Endpoints

```
GET  /v1/healthz        liveness + contexts_loaded counts
GET  /v1/metadata       team identity + approach
POST /v1/context        idempotent (scope, context_id, version) push
POST /v1/tick           proactive composer; returns up to 20 actions per tick
POST /v1/reply          stateful FSM-driven response (send | wait | end)
```

## Run locally

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then add your keys
python -m bot.main    # listens on :8080
```

## Generate the 30-pair submission.jsonl

```bash
python3 dataset/generate_dataset.py --seed-dir dataset --out expanded
python3 generate_submission.py
```

## Deploy

This repo ships as a Hugging Face Spaces Docker app — push to the Space and it runs. The same `Dockerfile` works on Render / Fly / Railway / Replit.

## Layout

```
bot/
├── main.py                  FastAPI app · 5 endpoints
├── store.py                 versioned context + conversation stores
├── compose.py               pure compose(category, merchant, trigger, customer?) → dict
├── reply.py                 FSM-aware reply composer
├── decision/
│   ├── router.py            trigger ranking + actionable selector
│   ├── strategies.py        25+ trigger-kind strategies
│   ├── voice.py             category voice profiles + language detector
│   ├── facts.py             specificity ranker + allowed-facts extractor
│   └── cooldown.py          per-merchant cooldown + suppression memory
├── composer/
│   ├── llm.py               Gemini → Groq → OpenRouter router (temp=0, deterministic cache)
│   ├── prompts.py           system + user prompt builders
│   ├── guard.py             grounding + voice + JSON-parse guard
│   └── templates.py         per-trigger deterministic fallback templates
└── conversation/
    ├── detectors.py         auto-reply / intent / hostile / off-topic regex+hash
    └── fsm.py               state machine (cross-conversation auto-reply tracking)
```
