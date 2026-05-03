"""Grounding + voice + format guard. Runs after LLM."""
from __future__ import annotations
from dataclasses import dataclass
import re, json
from typing import Any
from ..decision.facts import numeric_anchors, named_entities, collect_strings


_NUM_RE = re.compile(r"(?<![\w/])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?![\w/])")
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_RUPEE_RE = re.compile(r"₹\s*(\d+(?:[,.]\d+)*)")
_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_MONTH_YEAR_RE = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+20\d{2}\b",
    re.IGNORECASE,
)
_CURRENCY_RE = re.compile(r"(?:\N{INDIAN RUPEE SIGN}|Rs\.?|INR|â‚¹)\s*(\d+(?:[,.]\d+)*)", re.IGNORECASE)
_SOURCE_RE = re.compile(
    r"\b(?:JIDA|DCI|NEJM|Lancet|BMJ|WHO|FSSAI|RBI|Mfr\s+[A-Z]|[A-Z]{2,6})(?:[^\n.!?]{0,45}?\bp\.\d+)?\b",
)
_CAP_ENTITY_RE = re.compile(
    r"\b(?:[A-Z][a-zA-Z.'-]{2,}|[A-Z]{2,})(?:\s+(?:[A-Z][a-zA-Z.'-]{2,}|[A-Z]{2,})){1,4}\b"
)
_PAGE_RE = re.compile(r"\bp\.\d+\b", re.IGNORECASE)
_KNOWN_RESEARCH_SOURCES = {"jida", "dci", "nejm", "lancet", "bmj", "who", "fssai", "rbi"}
_COMMON_ENTITY_WORDS = {
    "Hi",
    "Quick",
    "Want",
    "Reply",
    "Done",
    "Sending",
    "Drafting",
    "Confirm",
    "Namaste",
    "Thanks",
    "Google",
    "WhatsApp",
    "Swiggy",
    "Zomato",
    "Insta",
    "Instagram",
    "Vera",
    "magicpin",
}
_ALLOWLIST_BRANDS = {"google", "whatsapp", "swiggy", "zomato", "insta", "instagram", "magicpin", "vera"}


@dataclass(frozen=True)
class Claim:
    text: str
    kind: str
    value: str
    span: tuple[int, int]


@dataclass(frozen=True)
class ContextField:
    scope: str
    dotted_path: str
    value: str


def parse_json_loose(text: str) -> dict | None:
    """Extract first JSON object from text, even if wrapped in markdown."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # Greedy attempt
    try:
        return json.loads(text)
    except Exception:
        pass
    # Find first { and balance
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if start == -1:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                try:
                    return json.loads(text[start:i+1])
                except Exception:
                    start = -1
                    depth = 0
    return None


def _clean_number(value: str) -> str:
    return value.replace(",", "").replace(" ", "").strip()


def _add_claim(claims: list[Claim], seen: set[tuple[int, int, str]], match: re.Match, kind: str, value: str | None = None) -> None:
    span = match.span()
    key = (span[0], span[1], kind)
    if key in seen:
        return
    text = match.group(0).strip()
    claims.append(Claim(text=text, kind=kind, value=value or text, span=span))
    seen.add(key)


def extract_claims(body: str) -> list[Claim]:
    """Extract claim-like facts from a body for context lineage checks."""
    claims: list[Claim] = []
    seen: set[tuple[int, int, str]] = set()
    covered_spans: list[tuple[int, int]] = []

    for m in _CURRENCY_RE.finditer(body):
        _add_claim(claims, seen, m, "currency", _clean_number(m.group(1)))
        covered_spans.append(m.span())
    for m in _PCT_RE.finditer(body):
        _add_claim(claims, seen, m, "percent", _clean_number(m.group(1)))
        covered_spans.append(m.span())
    for m in _DATE_RE.finditer(body):
        _add_claim(claims, seen, m, "date", m.group(1))
        covered_spans.append(m.span())
    for m in _MONTH_YEAR_RE.finditer(body):
        _add_claim(claims, seen, m, "date", m.group(0))
        covered_spans.append(m.span())
    for m in _SOURCE_RE.finditer(body):
        text = m.group(0).strip(" ,.;:")
        if text.lower() in _ALLOWLIST_BRANDS:
            continue
        claims.append(Claim(text=text, kind="source_citation", value=text, span=m.span()))
        seen.add((m.start(), m.end(), "source_citation"))
        covered_spans.append(m.span())
    for m in _PAGE_RE.finditer(body):
        _add_claim(claims, seen, m, "source_citation", m.group(0))
        covered_spans.append(m.span())

    for m in _NUM_RE.finditer(body):
        span = m.span()
        if any(max(span[0], s0) < min(span[1], s1) for s0, s1 in covered_spans):
            continue
        _add_claim(claims, seen, m, "number", _clean_number(m.group(1)))

    for m in _CAP_ENTITY_RE.finditer(body):
        text = m.group(0).strip(" ,.;:")
        parts = text.split()
        if all(part in _COMMON_ENTITY_WORDS for part in parts):
            continue
        if text.lower() in _ALLOWLIST_BRANDS:
            continue
        if any(max(m.start(), s0) < min(m.end(), s1) for s0, s1 in covered_spans):
            continue
        claims.append(Claim(text=text, kind="named_entity", value=text, span=m.span()))

    return sorted(claims, key=lambda claim: (claim.span[0], claim.span[1], claim.kind))


def _flatten_context(scope: str, obj: Any, path: str = "") -> list[ContextField]:
    fields: list[ContextField] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            next_path = f"{path}.{key}" if path else str(key)
            fields.extend(_flatten_context(scope, value, next_path))
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            next_path = f"{path}[{idx}]" if path else f"[{idx}]"
            fields.extend(_flatten_context(scope, value, next_path))
    elif obj is not None:
        fields.append(ContextField(scope=scope, dotted_path=path or scope, value=str(obj)))
    return fields


def _context_fields(contexts: dict) -> list[ContextField]:
    fields: list[ContextField] = []
    for scope in ("category", "merchant", "trigger", "customer"):
        obj = contexts.get(scope)
        if obj is not None:
            fields.extend(_flatten_context(scope, obj))
    return fields


def _numbers_in(text: str) -> list[float]:
    nums: list[float] = []
    for m in _NUM_RE.finditer(text):
        try:
            nums.append(float(_clean_number(m.group(1))))
        except ValueError:
            pass
    for m in _PCT_RE.finditer(text):
        try:
            nums.append(float(_clean_number(m.group(1))))
        except ValueError:
            pass
    for m in _CURRENCY_RE.finditer(text):
        try:
            nums.append(float(_clean_number(m.group(1))))
        except ValueError:
            pass
    return nums


def _month_number(name: str) -> str:
    months = {
        "jan": "01",
        "feb": "02",
        "mar": "03",
        "apr": "04",
        "may": "05",
        "jun": "06",
        "jul": "07",
        "aug": "08",
        "sep": "09",
        "sept": "09",
        "oct": "10",
        "nov": "11",
        "dec": "12",
    }
    return months.get(name[:4].lower(), months.get(name[:3].lower(), ""))


def _year_month(value: str) -> str | None:
    iso = re.search(r"\b(20\d{2})-(\d{2})-\d{2}\b", value)
    if iso:
        return f"{iso.group(1)}-{iso.group(2)}"
    month_year = _MONTH_YEAR_RE.search(value)
    if month_year:
        parts = month_year.group(0).split()
        return f"{parts[-1]}-{_month_number(parts[0])}"
    return None


def _claim_allowed(claim: Claim) -> bool:
    if claim.kind in {"number", "currency", "percent"}:
        try:
            return float(_clean_number(claim.value)) <= 99 and claim.kind == "number"
        except ValueError:
            return False
    return claim.value.strip().lower() in _ALLOWLIST_BRANDS


def _match_claim(claim: Claim, fields: list[ContextField]) -> ContextField | None:
    if claim.kind in {"number", "currency", "percent"}:
        try:
            claim_num = float(_clean_number(claim.value))
        except ValueError:
            return None
        for field in fields:
            for value in _numbers_in(field.value):
                if abs(value - claim_num) < 0.000001:
                    return field
                if claim.kind == "percent" and "delta_7d" in field.dotted_path:
                    if abs(abs(value) * 100 - claim_num) <= 1.0:
                        return field
                    if abs(abs(value) - claim_num) <= 1.0:
                        return field
        return None

    if claim.kind == "date":
        claim_lower = claim.value.lower()
        claim_ym = _year_month(claim.value)
        for field in fields:
            value_lower = field.value.lower()
            if claim_lower in value_lower:
                return field
            if claim_ym and claim_ym == _year_month(field.value):
                return field
        return None

    needle = claim.value.strip().lower()
    for field in fields:
        if needle and needle in field.value.lower():
            return field
        if claim.kind == "source_citation":
            source_token = needle.split()[0] if needle else ""
            if source_token and source_token in field.value.lower():
                return field
    return None


def lineage(claims: list[Claim], contexts: dict) -> dict[Claim, ContextField | None]:
    """Map each claim to the first context field that supports it, if any."""
    fields = _context_fields(contexts)
    return {claim: _match_claim(claim, fields) for claim in claims}


def check_groundedness_v2(body: str, contexts: dict) -> tuple[bool, list[Claim], list[tuple[Claim, ContextField]]]:
    """Ground a body by tracing extracted claims back to context fields."""
    claims = extract_claims(body)
    traced_map = lineage(claims, contexts)
    unsourced: list[Claim] = []
    traced: list[tuple[Claim, ContextField]] = []
    for claim, field in traced_map.items():
        if field is not None:
            traced.append((claim, field))
            continue
        if _claim_allowed(claim):
            continue
        unsourced.append(claim)

    hard_fail_kinds = {"currency", "percent", "source_citation"}
    is_grounded = not any(claim.kind in hard_fail_kinds for claim in unsourced)
    return is_grounded, unsourced, traced


def check_groundedness(body: str, allowed_nums: set[str], allowed_names: set[str]) -> tuple[bool, list[str]]:
    """Return (is_grounded, list_of_violations)."""
    violations: list[str] = []

    # Check numeric tokens
    found_nums: set[str] = set()
    for m in _NUM_RE.finditer(body):
        found_nums.add(m.group(1).replace(",", ""))
    for m in _PCT_RE.finditer(body):
        found_nums.add(m.group(1))
    for m in _RUPEE_RE.finditer(body):
        found_nums.add(m.group(1).replace(",", "").replace(".", ""))
    for m in _DATE_RE.finditer(body):
        found_nums.add(m.group(1))

    for n in found_nums:
        if n in allowed_nums:
            continue
        # Allow small ints (counts, durations, hours)
        try:
            if float(n) <= 99 and "." not in n:
                continue
        except ValueError:
            pass
        # Allow common time-of-day formats baked into context (e.g., "2pm", standalone hours 1-23)
        violations.append(f"unknown_number:{n}")

    # We deliberately do NOT flag arbitrary capitalized tokens — too many false positives
    # for ordinary English ("Want", "Reply"), product/service names ("Whitening", "Cleaning"),
    # and common Hindi-Latin ("Namaste"). The numeric check above is the strong grounding gate.

    return (len(violations) == 0), violations


def voice_violations(body: str, taboo_vocab: list[str]) -> list[str]:
    bl = body.lower()
    return [w for w in (taboo_vocab or []) if w.lower() in bl]


def cta_count(body: str) -> int:
    """Approximate count of CTAs by question marks + 'Reply ' / 'Want me' patterns."""
    qs = body.count("?")
    return qs


def normalize(body: str) -> str:
    return re.sub(r"[ \t]+", " ", body).strip()
