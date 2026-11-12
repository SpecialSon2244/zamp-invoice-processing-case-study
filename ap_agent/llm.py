"""Optional LLM extraction fallback. Off by default.

Why it is optional:
  * The process must run on any laptop, live in an interview, with no API key and no network.
  * Rules are cheap, fast, deterministic and easy to audit. An AP team can see exactly why a
    number was read.
  * The LLM is only asked about fields the rules could not read or read with low confidence.
    Whatever it returns still goes through every validation rule, and its answers get a
    confidence of 0.80, which is below the 0.85 auto-approval bar. So an LLM read on a
    critical field always ends up in front of a person. The LLM can suggest; it cannot approve money.

Configure with environment variables:
  LLM_API_KEY (or OPENAI_API_KEY), LLM_BASE_URL (OpenAI-compatible, default https://api.openai.com/v1),
  LLM_MODEL (default gpt-4o-mini).
"""
from __future__ import annotations

import json
import os
import urllib.request

from .extract import Extraction, Field, parse_amount, parse_date, reconcile

LLM_CONFIDENCE = 0.80
FIELDS = ["invoice_number", "invoice_date", "po_number", "supplier_tax_id", "currency",
          "net_amount", "tax_amount", "total_amount", "bank_account"]

PROMPT = """You read vendor invoices for an accounts payable team.
Return JSON only, with these keys: {keys}.
Use null when the value is not printed on the document. Do not guess or calculate missing values.
Dates as YYYY-MM-DD (the document uses day-first dates). Amounts as plain numbers.

Document text:
---
{text}
---"""


def api_key() -> str | None:
    return os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")


def call_llm(text: str, keys: list[str]) -> dict:
    url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
    body = {"model": os.environ.get("LLM_MODEL", "gpt-4o-mini"), "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": PROMPT.format(keys=", ".join(keys), text=text[:12000])}]}
    req = urllib.request.Request(url, json.dumps(body).encode(), method="POST", headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {api_key()}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    return json.loads(data["choices"][0]["message"]["content"])


def llm_fill(ex: Extraction, text: str, min_conf: float, caller=call_llm) -> list[str]:
    """Ask the LLM only for weak fields. Returns a list of notes for the audit trail."""
    weak = [f for f in FIELDS if ex.conf(f) < min_conf]
    if not weak:
        return ["LLM not needed: every field read with enough confidence by rules"]
    if caller is call_llm and not api_key():
        return [f"LLM step skipped: no API key set. Weak fields left for a person: {', '.join(weak)}"]
    try:
        answer = caller(text, weak)
    except Exception as e:  # network, quota, bad JSON: never break the run
        return [f"LLM step failed ({type(e).__name__}); continuing with rule-based values"]
    notes = []
    for f in weak:
        raw = answer.get(f)
        if raw in (None, "", "null"):
            continue
        val = raw
        if f in ("net_amount", "tax_amount", "total_amount"):
            val = parse_amount(str(raw)) if not isinstance(raw, (int, float)) else float(raw)
        elif f == "invoice_date":
            val = parse_date(str(raw))
        if val is None:
            continue
        ex.fields[f] = Field(val, LLM_CONFIDENCE, "llm", f"LLM suggested {raw}")
        notes.append(f"LLM filled {f} = {raw} (confidence {LLM_CONFIDENCE}, needs human check)")
    reconcile(ex)
    return notes or ["LLM returned nothing usable for the weak fields"]
