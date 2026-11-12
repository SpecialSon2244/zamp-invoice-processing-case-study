"""Runs the real PDFs through the whole pipeline and checks every route against ground truth."""
import json
from datetime import date

from ap_agent.config import DATA, Policy
from ap_agent.pipeline import run_batch


def test_sample_set_routes_match_ground_truth():
    truth = {t["file"]: t["expected_route"] for t in json.loads((DATA / "ground_truth.json").read_text())["invoices"]}
    _, results = run_batch(sorted((DATA / "inbox").glob("*.pdf")), Policy(as_of=date(2026, 11, 12)))
    got = {r["file"]: r["decision"]["route"] for r in results}
    assert got == truth


def test_llm_fallback_only_fills_weak_fields_and_never_auto_approves():
    from ap_agent.llm import LLM_CONFIDENCE, llm_fill
    from tests.helpers import make_ex
    ex = make_ex(invoice_number=None)
    notes = llm_fill(ex, "text", 0.85, caller=lambda text, keys: {"invoice_number": "SLP/26-27/0999", "total_amount": 1})
    assert ex.get("invoice_number") == "SLP/26-27/0999" and ex.conf("invoice_number") == LLM_CONFIDENCE < 0.85
    assert ex.get("total_amount") == 30385.0          # strong field left alone
    assert any("LLM filled" in n for n in notes)


def test_llm_skipped_without_key(monkeypatch):
    from ap_agent.llm import llm_fill
    from tests.helpers import make_ex
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    notes = llm_fill(make_ex(invoice_number=None), "text", 0.85)
    assert "skipped" in notes[0]
