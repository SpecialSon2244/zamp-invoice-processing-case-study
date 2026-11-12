"""Runs one invoice through every stage and records what happened at each step.

Stages:
  1 Ingest    2 Extract    3 Vendor    4 Completeness    5 Tax
  6 Duplicates    7 PO + GRN (3-way)    8 Policy    9 Decision

`on_stage` is called after each stage, so the CLI and the UI can show the run live.
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import rules
from .config import Policy
from .extract import extract_fields, read_document
from .masterdata import MasterData
from .store import Store

ROUTES = ("AUTO_APPROVE", "NEEDS_REVIEW", "REJECT")
STAGE_TITLES = {
    "ingest": "1. Ingest document", "extract": "2. Extract fields", "vendor": "3. Identify vendor",
    "completeness": "4. Completeness and confidence", "tax": "5. GST / VAT compliance",
    "duplicates": "6. Duplicate check", "match": "7. PO and goods receipt (3-way match)",
    "policy": "8. Approval policy", "decision": "9. Decision",
}


def _status(findings):
    sev = {f.severity for f in findings}
    return "fail" if "reject" in sev else "warn" if "review" in sev else "ok"


def decide(findings: list[rules.Finding]) -> dict:
    """Reject beats review beats approve. The reasons travel with the decision."""
    rejects = [f for f in findings if f.severity == "reject"]
    reviews = [f for f in findings if f.severity == "review"]
    if rejects:
        route, reasons = "REJECT", rejects
    elif reviews:
        route, reasons = "NEEDS_REVIEW", reviews
    else:
        route, reasons = "AUTO_APPROVE", []
    owner = reasons[0].owner if reasons else "none (straight to payment run)"
    if route == "REJECT":
        owner = "AP (send back to vendor)"
    return {"route": route, "owner": owner, "reasons": [r.as_dict() for r in reasons],
            "also_noted": [r.as_dict() for r in reviews] if route == "REJECT" else []}


def process_invoice(path: Path, md: MasterData, policy: Policy, store: Store | None = None, run_id: str = "",
                    use_llm: bool = False, on_stage: Callable[[dict], None] | None = None) -> dict:
    path = Path(path)
    stages, all_findings = [], []

    def emit(key, findings, summary, data=None, t0=None):
        st = {"stage": key, "title": STAGE_TITLES[key], "status": _status(findings), "summary": summary,
              "findings": [f.as_dict() for f in findings], "data": data or {},
              "ms": round((time.perf_counter() - t0) * 1000) if t0 else 0}
        stages.append(st)
        all_findings.extend(findings)
        if store:
            store.audit(run_id, path.name, key, summary, {"status": st["status"], "findings": st["findings"]})
        if on_stage:
            on_stage(st)

    t0 = time.perf_counter()
    doc = read_document(path)
    emit("ingest", [], f"{doc.pages} page(s), {'text layer found' if doc.source == 'text' else 'no text layer, OCR used'}"
         + (f" (mean OCR confidence {doc.ocr_mean_conf:.2f})" if doc.ocr_mean_conf else ""),
         {"source": doc.source, "pages": doc.pages}, t0)

    t0 = time.perf_counter()
    ex = extract_fields(doc)
    notes = list(ex.notes)
    if use_llm:
        from .llm import llm_fill
        notes += llm_fill(ex, doc.text, policy.min_field_confidence)
    fields = {k: v.as_dict() for k, v in ex.fields.items()}
    read = sum(1 for k in rules.CRITICAL_FIELDS if ex.get(k) is not None)
    emit("extract", [rules.I("EXTRACT_NOTE", n) for n in notes],
         f"{read}/{len(rules.CRITICAL_FIELDS)} critical fields read, {len(ex.lines)} line item(s)",
         {"fields": fields, "lines": ex.lines, "taxes": ex.taxes}, t0)

    t0 = time.perf_counter()
    vendor, f = rules.identify_vendor(ex, md)
    emit("vendor", f, f"{vendor['vendor_id']} {vendor['name']}" if vendor else "Vendor not in master", {}, t0)

    t0 = time.perf_counter()
    f = rules.check_completeness(ex, policy, doc.source)
    emit("completeness", f, "All required fields present and readable" if not f else
         f"{len(f)} issue(s): " + ", ".join(x.code for x in f), {}, t0)

    t0 = time.perf_counter()
    f, tds = rules.check_tax(ex, vendor, policy)
    emit("tax", f, "; ".join(x.message for x in f if x.severity != "info") or
         next((x.message for x in f if x.code in ("GST_OK", "VAT_OK")), "Tax checks passed"), tds, t0)

    t0 = time.perf_counter()
    f = rules.check_duplicates(ex, vendor, md, policy)
    emit("duplicates", f, f[0].message, {}, t0)

    t0 = time.perf_counter()
    f, match = rules.three_way_match(ex, vendor, md, policy)
    emit("match", f, ("PO " + match["po_number"] + (" (inferred)" if match["po_inferred"] else "") + ": "
                      if match["po_number"] else "") + ("; ".join(x.code for x in f if x.severity != "info")
                                                        or "matched"), match, t0)

    t0 = time.perf_counter()
    f = rules.check_policy(ex, policy)
    emit("policy", f, "Within auto-approval limits" if not f else "; ".join(x.code for x in f), {}, t0)

    decision = decide(all_findings)
    total = ex.get("total_amount")
    payable = round(total - tds.get("tds_amount", 0), 2) if total is not None else None
    decision["payable_amount"] = payable
    decision["min_critical_confidence"] = round(min((ex.conf(k) for k in rules.CRITICAL_FIELDS), default=0), 2)
    emit("decision", [], {"AUTO_APPROVE": "Auto-approved for the next payment run",
                          "NEEDS_REVIEW": f"Sent to review: {decision['owner']}",
                          "REJECT": "Rejected: return to vendor"}[decision["route"]] +
         (f" ({len(decision['reasons'])} reason(s))" if decision["reasons"] else ""), decision)

    # remember this invoice for later ones in the same batch (duplicates and PO consumption)
    if decision["route"] != "REJECT" and vendor:
        md.batch.append({
            "vendor_id": vendor["vendor_id"], "invoice_number": ex.get("invoice_number") or "",
            "invoice_date": ex.get("invoice_date").isoformat() if ex.get("invoice_date") else "",
            "currency": ex.get("currency"), "total": total or 0.0, "po_number": match["po_number"] or "",
            "billed_lines": ";".join(f"{l['po_line']}:{l['qty']}" for l in match["lines"] if "po_line" in l),
            "service_period": ex.get("service_period") or "", "status": decision["route"].lower()})

    return {"file": path.name, "path": str(path.resolve()), "vendor_id": vendor["vendor_id"] if vendor else None,
            "vendor_name": vendor["name"] if vendor else ex.get("supplier_name"), "source": doc.source,
            "fields": fields, "lines": ex.lines, "taxes": ex.taxes, "match": match, "tds": tds,
            "stages": stages, "decision": decision}


def new_run_id() -> str:
    return datetime.now().strftime("run-%Y%m%d-%H%M%S-%f")[:-3]


def run_batch(paths: list[Path], policy: Policy, store: Store | None = None, use_llm: bool = False,
              source: str = "cli", on_stage=None, on_invoice=None, md: MasterData | None = None) -> tuple[str, list]:
    md = md or MasterData.load()
    run_id = new_run_id()
    if store:
        store.start_run(run_id, source, use_llm)
    results = []
    for p in sorted(paths):
        res = process_invoice(p, md, policy, store, run_id, use_llm,
                              (lambda st, p=p: on_stage(p, st)) if on_stage else None)
        results.append(res)
        if store:
            store.save_invoice(run_id, res)
        if on_invoice:
            on_invoice(res)
    if store:
        counts = {r: sum(1 for x in results if x["decision"]["route"] == r) for r in ROUTES}
        store.finish_run(run_id, counts)
    return run_id, results
