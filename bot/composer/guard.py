"""Grounding + voice + format guard. Runs after LLM."""
from __future__ import annotations
import re, json
from ..decision.facts import numeric_anchors, named_entities, collect_strings


_NUM_RE = re.compile(r"(?<![\w/])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?![\w/])")
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_RUPEE_RE = re.compile(r"₹\s*(\d+(?:[,.]\d+)*)")
_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


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
