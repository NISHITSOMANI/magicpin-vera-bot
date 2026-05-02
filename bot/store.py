"""Versioned in-memory context store. Idempotent on (scope, context_id, version)."""
from __future__ import annotations
from dataclasses import dataclass, field
from threading import RLock
from typing import Any


@dataclass
class StoredCtx:
    version: int
    payload: dict[str, Any]


class ContextStore:
    def __init__(self) -> None:
        self._data: dict[tuple[str, str], StoredCtx] = {}
        self._lock = RLock()

    def put(self, scope: str, context_id: str, version: int, payload: dict) -> tuple[bool, int | None]:
        """Returns (accepted, current_version_if_rejected)."""
        with self._lock:
            cur = self._data.get((scope, context_id))
            if cur and cur.version >= version:
                return False, cur.version
            self._data[(scope, context_id)] = StoredCtx(version=version, payload=payload)
            return True, None

    def get(self, scope: str, context_id: str) -> dict | None:
        with self._lock:
            cur = self._data.get((scope, context_id))
            return cur.payload if cur else None

    def get_version(self, scope: str, context_id: str) -> int | None:
        with self._lock:
            cur = self._data.get((scope, context_id))
            return cur.version if cur else None

    def all_of(self, scope: str) -> dict[str, dict]:
        with self._lock:
            return {cid: v.payload for (s, cid), v in self._data.items() if s == scope}

    def counts(self) -> dict[str, int]:
        c = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        with self._lock:
            for (scope, _), _ in self._data.items():
                c[scope] = c.get(scope, 0) + 1
        return c


@dataclass
class ConversationTurn:
    role: str  # "vera" | "merchant" | "customer"
    body: str
    ts: str
    cta: str | None = None


@dataclass
class ConversationState:
    conversation_id: str
    merchant_id: str | None
    customer_id: str | None
    trigger_id: str | None
    send_as: str
    state: str = "opened"  # opened | qualifying | action | confirming | handoff | closed
    turns: list[ConversationTurn] = field(default_factory=list)
    inbound_hashes: list[str] = field(default_factory=list)
    last_outbound_body: str | None = None
    autoreply_strikes: int = 0
    unanswered_nudges: int = 0


class ConversationStore:
    def __init__(self) -> None:
        self._data: dict[str, ConversationState] = {}
        self._lock = RLock()

    def get_or_create(self, cid: str, **kw) -> ConversationState:
        with self._lock:
            if cid not in self._data:
                self._data[cid] = ConversationState(conversation_id=cid, **kw)
            return self._data[cid]

    def get(self, cid: str) -> ConversationState | None:
        with self._lock:
            return self._data.get(cid)

    def update(self, conv: ConversationState) -> None:
        with self._lock:
            self._data[conv.conversation_id] = conv


# Singleton
CONTEXT = ContextStore()
CONVOS = ConversationStore()
SENT_SUPPRESSION_KEYS: dict[str, set[str]] = {}  # merchant_id -> {keys}
LAST_SEND_TS: dict[str, str] = {}  # merchant_id -> ISO ts
COMPOSE_CACHE: dict[str, dict] = {}  # cache_key -> composed message

# Cross-conversation auto-reply memory: merchant_id -> [hashes of recent inbounds suspected as auto]
MERCHANT_AUTO_HASHES: dict[str, list[str]] = {}
MERCHANT_AUTO_STRIKES: dict[str, int] = {}
