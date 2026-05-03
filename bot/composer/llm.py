"""Multi-provider LLM router. Order: Gemini → Groq → OpenRouter. Deterministic."""
from __future__ import annotations
import os, json, hashlib, time
from typing import Any
import httpx

GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

# Deterministic call cache (process-wide)
_CALL_CACHE: dict[str, str] = {}
PROVIDER_COUNTS: dict[str, int] = {"gemini": 0, "groq": 0, "openrouter": 0, "template": 0}


def record_provider_use(provider: str) -> None:
    """Increment provider usage counters for diagnostics."""
    PROVIDER_COUNTS[provider] = PROVIDER_COUNTS.get(provider, 0) + 1


def _cache_key(provider: str, model: str, system: str, user: str) -> str:
    h = hashlib.sha256()
    h.update(f"{provider}|{model}|{system}|{user}".encode("utf-8"))
    return h.hexdigest()


def _gemini_call(system: str, user: str, model: str = "gemini-2.5-flash", timeout: float = 18.0) -> str:
    """Google AI Studio Gemini API."""
    if not GEMINI_KEY:
        raise RuntimeError("no_gemini_key")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": 0.0,
            "topP": 1.0,
            "topK": 1,
            "maxOutputTokens": 2048,
            "candidateCount": 1,
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, params={"key": GEMINI_KEY}, json=body)
        r.raise_for_status()
        data = r.json()
    cands = data.get("candidates", [])
    if not cands:
        raise RuntimeError(f"gemini_empty:{data}")
    parts = (cands[0].get("content") or {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts)
    if not text.strip():
        raise RuntimeError("gemini_blank")
    return text.strip()


def _groq_call(system: str, user: str, model: str = "llama-3.3-70b-versatile", timeout: float = 18.0) -> str:
    if not GROQ_KEY:
        raise RuntimeError("no_groq_key")
    url = "https://api.groq.com/openai/v1/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": 1024,
        "seed": 7,
    }
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, headers={"Authorization": f"Bearer {GROQ_KEY}"}, json=body)
        r.raise_for_status()
        data = r.json()
    return data["choices"][0]["message"]["content"].strip()


def _openrouter_call(system: str, user: str,
                      model: str = "meta-llama/llama-3.3-70b-instruct:free",
                      timeout: float = 22.0) -> str:
    if not OPENROUTER_KEY:
        raise RuntimeError("no_openrouter_key")
    url = "https://openrouter.ai/api/v1/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": 1024,
        "seed": 7,
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "HTTP-Referer": "https://huggingface.co/spaces/Nishit2005/vera-bot",
        "X-Title": "Vera Bot",
    }
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
    return data["choices"][0]["message"]["content"].strip()


PROVIDER_CHAIN = [
    ("gemini", _gemini_call, "gemini-2.5-flash"),
    ("groq", _groq_call, "llama-3.3-70b-versatile"),
    ("openrouter", _openrouter_call, "deepseek/deepseek-chat-v3.1:free"),
    ("openrouter", _openrouter_call, "meta-llama/llama-3.3-70b-instruct:free"),
]


def call_llm(system: str, user: str, *, deadline_seconds: float = 22.0) -> tuple[str, str]:
    """Try providers in order. Returns (text, provider_used). Raises if all fail.

    On 429/rate-limit, backs off briefly then tries the next provider.
    """
    start = time.time()
    last_err: Exception | None = None
    for provider, fn, model in PROVIDER_CHAIN:
        if time.time() - start > deadline_seconds:
            break
        ck = _cache_key(provider, model, system, user)
        if ck in _CALL_CACHE:
            record_provider_use(provider)
            return _CALL_CACHE[ck], provider
        try:
            remaining = max(4.0, deadline_seconds - (time.time() - start))
            text = fn(system, user, model=model, timeout=remaining)
            _CALL_CACHE[ck] = text
            record_provider_use(provider)
            return text, provider
        except httpx.HTTPStatusError as e:
            last_err = e
            # On rate-limit, brief backoff then continue
            if e.response.status_code in (429, 503):
                time.sleep(0.4)
            continue
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"all_providers_failed: {last_err}")
