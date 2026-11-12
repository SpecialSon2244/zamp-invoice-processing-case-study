"""Stages 3-8: the checks an AP clerk does by hand, written as small, testable functions.

Each check returns Findings. A Finding has a severity:
  reject  -> the invoice goes back to the vendor (only the vendor can fix it)
  review  -> a named person in our company has to decide
  info    -> recorded in the audit trail, does not stop approval
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date
from difflib import SequenceMatcher

from .config import BUYERS, CRITICAL_FIELDS, Policy
from .extract import Extraction
from .masterdata import MasterData
from .taxids import validate_eu_vat, validate_gstin


@dataclass
class Finding:
    code: str
    severity: str          # reject | review | info
    message: str
    owner: str = "AP"
    action: str = ""

    def as_dict(self):
        return asdict(self)


def R(code, msg, owner="AP", action=""):
    return Finding(code, "reject", msg, owner, action or "Return to vendor and ask for a corrected invoice")


def V(code, msg, owner="AP", action=""):
    return Finding(code, "review", msg, owner, action)


def I(code, msg):
    return Finding(code, "info", msg, "", "")


def money(cur: str, x: float) -> str:
    """INR in Indian grouping (7,08,000.00), everything else in 1,234.56 style."""
    if cur != "INR":
        return f"{cur} {x:,.2f}"
    whole, dec = f"{abs(x):.2f}".split(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return "INR " + ("-" if x < 0 else "") + ",".join(groups + [tail]) + "." + dec


def norm_number(s: str) -> str:
    """'INV/2026/0412' and 'inv-2026-412' normalise to the same key."""
    s = re.sub(r"[^A-Z0-9]", " ", (s or "").upper())
    return "".join(p.lstrip("0") or "0" if p.isdigit() else p for p in s.split())


def norm_period(s: str | None) -> str:
    """'Oct 2026', 'OCT-2026' and 'Oct2026' are the same service period."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def sim(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def compact_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# ------------------------------------------------------------------ stage 3: vendor
def identify_vendor(ex: Extraction, md: MasterData) -> tuple[dict | None, list[Finding]]:
    out = []
    tax_id = ex.get("supplier_tax_id")
    vendor = md.vendor_by_tax_id(tax_id) if tax_id else None
    how = "tax ID"
    if not vendor and tax_id and len(tax_id) == 15:
        vendor = md.vendor_by_pan(tax_id[2:12])   # same legal entity (PAN) but GSTIN differs
        how = "PAN inside the GSTIN"
    if not vendor:
        name = compact_name(ex.get("supplier_name"))
        best = max(md.vendors.values(), key=lambda v: sim(name, compact_name(v["name"])), default=None)
        if best and sim(name, compact_name(best["name"])) >= 0.85:
            vendor, how = best, "name only"
            out.append(V("VENDOR_NAME_MATCH_ONLY",
                         f"Vendor matched to {best['name']} by name only; tax ID on invoice does not match master"))
    if not vendor:
        out.append(V("UNKNOWN_VENDOR",
                     f"'{ex.get('supplier_name')}' ({tax_id or 'no tax ID'}) is not in the vendor master",
                     "Procurement", "Do not pay. Check if this vendor should be onboarded and who ordered the goods."))
        return None, out
    out.append(I("VENDOR_FOUND", f"Vendor {vendor['vendor_id']} {vendor['name']} identified by {how}"))
    if vendor["status"] != "active":
        out.append(R("VENDOR_BLOCKED", f"Vendor {vendor['vendor_id']} is {vendor['status']} in the master",
                     "Procurement", "Do not pay. Confirm vendor status with procurement."))
    # bank details: the most common way invoice fraud happens
    bank = ex.get("bank_account")
    if bank and bank != vendor["bank_account"]:
        out.append(V("BANK_MISMATCH",
                     f"Bank account on invoice ({bank}, {ex.get('bank_code')}) differs from vendor master "
                     f"(ending {vendor['bank_account'][-4:]}, {vendor['bank_code']})",
                     "AP lead / Treasury",
                     "Hold payment. Call the vendor on the phone number already in the master (not the one on "
                     "the invoice) and confirm the change in writing before updating anything."))
    elif not bank:
        out.append(I("BANK_NOT_ON_INVOICE", "No bank details on invoice; payment will use vendor master details"))
    return vendor, out


# ------------------------------------------------------------------ stage 4: completeness and confidence
def check_completeness(ex: Extraction, policy: Policy, source: str = "text") -> list[Finding]:
    out = []
    must_have = {"invoice_number": "invoice number", "invoice_date": "invoice date", "total_amount": "total amount"}
    for f, label in must_have.items():
        if ex.get(f) is None and source == "ocr":
            # On a scan we cannot tell "vendor left it out" from "OCR missed it", so a person looks first.
            out.append(V(f"UNREADABLE_{f.upper()}", f"Could not read the {label} from the scan", "AP",
                         f"Look at the scan. If the {label} is really missing, return to vendor; "
                         f"otherwise type it in"))
        elif ex.get(f) is None:
            out.append(R(f"MISSING_{f.upper()}", f"No {label} found on the document",
                         action=f"Return to vendor: an invoice without a {label} cannot be booked or "
                                f"claimed for input tax credit"))
    low = [f"{f} ({ex.conf(f):.2f})" for f in CRITICAL_FIELDS
           if ex.get(f) is not None and ex.conf(f) < policy.min_field_confidence]
    if low:
        out.append(V("LOW_CONFIDENCE", "Low read confidence on: " + ", ".join(low), "AP",
                     "Check these fields against the PDF and correct them in the review screen"))
    net, tax, total = ex.get("net_amount"), ex.get("tax_amount"), ex.get("total_amount")
    tol = policy.amount_tolerance_abs
    if None not in (net, tax, total) and abs(net + tax - total) > tol:
        out.append(V("ARITHMETIC_MISMATCH", f"Net {net:,.2f} + tax {tax:,.2f} != total {total:,.2f}"))
    if ex.lines and net is not None and abs(sum(l["amount"] or 0 for l in ex.lines) - net) > tol:
        out.append(V("LINES_DONT_SUM", f"Line items add up to {sum(l['amount'] for l in ex.lines):,.2f}, "
                                       f"net says {net:,.2f}"))
    if not ex.lines:
        out.append(V("NO_LINE_ITEMS", "Could not read any line items; cannot match quantities to the PO"))
    return out


# ------------------------------------------------------------------ stage 5: tax compliance
def check_tax(ex: Extraction, vendor: dict | None, policy: Policy) -> tuple[list[Finding], dict]:
    regime = ex.get("tax_regime")
    if regime == "GST":
        return check_gst(ex, vendor, policy)
    if regime == "VAT":
        return check_vat(ex, vendor, policy), {}
    return [V("TAX_REGIME_UNKNOWN", "Could not find a GSTIN or EU VAT ID on the invoice", "Tax")], {}


def check_gst(ex: Extraction, vendor: dict | None, policy: Policy) -> tuple[list[Finding], dict]:
    out, info = [], {}
    sup, buyer = ex.get("supplier_tax_id"), ex.get("buyer_tax_id")
    problems = validate_gstin(sup)
    if problems:
        out.append(R("GSTIN_INVALID", "; ".join(problems),
                     action="Return to vendor: input tax credit cannot be claimed against an invalid GSTIN"))
    elif vendor and vendor["tax_id"] and sup != vendor["tax_id"]:
        out.append(V("GSTIN_MASTER_MISMATCH", f"GSTIN {sup} differs from vendor master {vendor['tax_id']}", "Tax"))
    if buyer != BUYERS["IN"]["tax_id"]:
        out.append(R("BUYER_GSTIN_WRONG", f"Invoice is addressed to GSTIN {buyer}, not ours ({BUYERS['IN']['tax_id']})",
                     action="Return to vendor: ITC only works if our GSTIN is on the invoice"))
    if not sup or problems:
        return out, info
    types = {t["type"] for t in ex.taxes}
    intra = sup[:2] == BUYERS["IN"]["tax_id"][:2]
    if intra and "IGST" in types:
        out.append(R("GST_REGIME_MISMATCH",
                     f"Supplier and buyer are both in state {sup[:2]}, so CGST + SGST applies, but the invoice "
                     f"charges IGST", action="Return to vendor: wrong tax head. Paying it means the credit sits "
                                             "in the wrong ledger and the vendor has to fix it in their return"))
    if not intra and types & {"CGST", "SGST"}:
        out.append(R("GST_REGIME_MISMATCH",
                     f"Supplier state {sup[:2]} differs from ours (29), so IGST applies, but the invoice charges "
                     f"CGST/SGST"))
    if {"CGST", "SGST"} <= types:
        c = next(t for t in ex.taxes if t["type"] == "CGST")
        s = next(t for t in ex.taxes if t["type"] == "SGST")
        if abs(c["amount"] - s["amount"]) > 0.5 or c["rate"] != s["rate"]:
            out.append(V("CGST_SGST_UNEQUAL", "CGST and SGST should be equal halves", "Tax"))
    effective = sum(t["rate"] for t in ex.taxes)
    if ex.taxes and effective not in policy.gst_slabs:
        out.append(V("GST_RATE_UNUSUAL", f"Total GST rate {effective:g}% is not a standard slab", "Tax"))
    net = ex.get("net_amount")
    for t in ex.taxes:
        if net and abs(net * t["rate"] / 100 - t["amount"]) > policy.amount_tolerance_abs:
            out.append(V("TAX_CALC_ERROR", f"{t['type']} {t['rate']}% of {net:,.2f} should be "
                                           f"{net * t['rate'] / 100:,.2f}, invoice says {t['amount']:,.2f}", "Tax"))
    if not out:
        out.append(I("GST_OK", f"GSTIN valid, {'CGST + SGST (intra-state)' if intra else 'IGST (inter-state)'} "
                               f"at {effective:g}% is correct for this supply"))
    if vendor and vendor["tds_rate"] and net:
        tds = round(net * vendor["tds_rate"] / 100, 2)
        info = {"tds_section": vendor["tds_section"], "tds_rate": vendor["tds_rate"], "tds_amount": tds}
        out.append(I("TDS", f"Deduct TDS u/s {vendor['tds_section']} at {vendor['tds_rate']:g}% (rate from vendor master) on the "
                            f"taxable value: {money('INR', tds)}. Net payable to vendor: "
                            f"{money('INR', ex.get('total_amount') - tds)}"))
    return out, info


def check_vat(ex: Extraction, vendor: dict | None, policy: Policy) -> list[Finding]:
    out = []
    sup, buyer = ex.get("supplier_tax_id"), ex.get("buyer_tax_id")
    problems = validate_eu_vat(sup)
    if problems:
        out.append(R("VAT_ID_INVALID", "; ".join(problems)))
    if buyer != BUYERS["DE"]["tax_id"]:
        out.append(R("BUYER_VAT_WRONG", f"Invoice addressed to VAT ID {buyer}, not ours ({BUYERS['DE']['tax_id']})"))
    if not sup:
        return out
    vat = ex.get("tax_amount") or 0.0
    domestic = sup[:2] == "DE"
    if domestic:
        rates = {t["rate"] for t in ex.taxes}
        allowed = policy.eu_vat_rates.get("DE", ())
        if not rates or not rates <= set(allowed):
            out.append(V("VAT_RATE_UNUSUAL", f"German VAT rate {rates or 'none'} is not 19% or 7%", "Tax"))
        else:
            out.append(I("VAT_OK", f"Domestic German supply, VAT {', '.join(f'{r:g}%' for r in rates)} is correct"))
    else:
        if vat > policy.amount_tolerance_abs:
            out.append(R("EU_REVERSE_CHARGE",
                         f"{sup[:2]} supplier charged {vat:,.2f} VAT on a B2B supply to our German entity. "
                         f"Cross-border B2B goods inside the EU are zero-rated and we self-account (reverse charge)",
                         action="Return to vendor: ask for a corrected invoice at 0% with the reverse charge note "
                                "and both VAT IDs. Foreign VAT paid here is very hard to recover"))
        elif not ex.get("reverse_charge_note"):
            out.append(V("REVERSE_CHARGE_NOTE_MISSING", "0% VAT but no reverse charge wording on the invoice", "Tax"))
        else:
            out.append(I("VAT_OK", "Intra-EU B2B supply correctly invoiced under reverse charge"))
    return out


# ------------------------------------------------------------------ stage 6: duplicates
def check_duplicates(ex: Extraction, vendor: dict | None, md: MasterData, policy: Policy) -> list[Finding]:
    if not vendor:
        return [I("DUP_SKIPPED", "Duplicate check needs a known vendor")]
    out = []
    num, total, d = ex.get("invoice_number"), ex.get("total_amount"), ex.get("invoice_date")
    period = norm_period(ex.get("service_period"))
    key = norm_number(num) if num else None
    for r in md.all_booked():
        if r["vendor_id"] != vendor["vendor_id"]:
            continue
        if key and norm_number(r["invoice_number"]) == key:
            out.append(R("DUPLICATE_EXACT", f"Invoice {num} from this vendor is already in the ledger "
                                            f"(booked {r['invoice_date']}, status {r['status']})",
                         action="Do not pay again. Tell the vendor it was already processed"))
            return out
    for r in md.all_booked():
        if r["vendor_id"] != vendor["vendor_id"] or total is None:
            continue
        same_amount = abs(r["total"] - total) <= total * policy.dup_amount_pct / 100
        try:
            days = abs((date.fromisoformat(r["invoice_date"]) - d).days) if d else 999
        except ValueError:
            days = 999
        number_close = bool(num) and sim(norm_number(num), norm_number(r["invoice_number"])) >= policy.dup_number_similarity
        same_po = bool(ex.get("po_number")) and r["po_number"] == ex.get("po_number")
        r_period = norm_period(r.get("service_period"))
        different_period = bool(period and r_period and period != r_period)
        if same_amount and days <= policy.dup_window_days and (number_close or same_po) and not different_period:
            why = [f"same amount {total:,.2f}", f"{days} days apart"]
            if number_close:
                why.append(f"similar number ({r['invoice_number']} vs {num})")
            if same_po:
                why.append(f"same PO {r['po_number']}")
            if period and period == r_period:
                why.append(f"same service period ({ex.get('service_period')})")
            out.append(V("DUPLICATE_SUSPECTED", f"Looks like a re-issue of {r['invoice_number']}: " + ", ".join(why),
                         "AP", f"Compare with {r['invoice_number']} before paying. If it is a re-issue, reject it "
                               f"and ask the vendor for a credit note or confirmation"))
            break
    if not out:
        out.append(I("NO_DUPLICATE", "No exact or near-duplicate found for this vendor"))
    return out


# ------------------------------------------------------------------ stage 7: PO and GRN (3-way match)
def match_line(inv_line: dict, po_lines: list[dict]) -> tuple[dict | None, float]:
    if inv_line.get("item_code"):
        for p in po_lines:
            if p["item_code"] == inv_line["item_code"]:
                return p, 1.0
    best = max(po_lines, key=lambda p: sim(inv_line["description"], p["description"]), default=None)
    score = sim(inv_line["description"], best["description"]) if best else 0.0
    return (best, score) if score >= 0.6 else (None, score)


def _po_fits(ex: Extraction, lines: list[dict], md: MasterData) -> bool:
    for il in ex.lines:
        pl, _ = match_line(il, lines)
        if not pl or md.billed_qty(pl["po_number"], pl["line_no"]) + il["qty"] > pl["qty"]:
            return False
    return bool(ex.lines)


def three_way_match(ex: Extraction, vendor: dict | None, md: MasterData, policy: Policy) -> tuple[list[Finding], dict]:
    out, result = [], {"po_number": None, "po_inferred": False, "lines": []}
    if not vendor:
        return [V("NO_PO_MATCH", "Cannot match to a PO without a known vendor", "Procurement")], result
    po = ex.get("po_number")
    if po and po not in md.po_lines:
        out.append(V("PO_NOT_FOUND", f"PO {po} is not in the PO register", "Procurement",
                     "Check the PO number with the requester"))
        return out, result
    if not po:
        candidates = [p for p, lines in md.po_lines.items()
                      if lines[0]["vendor_id"] == vendor["vendor_id"] and _po_fits(ex, lines, md)]
        if len(candidates) == 1:
            po = candidates[0]
            result["po_inferred"] = True
            out.append(I("PO_INFERRED", f"No PO number on invoice. Only one open PO for this vendor fits the "
                                        f"items and remaining quantity: {po}"))
        elif not candidates:
            out.append(V("NO_PO_MATCH", "No PO number on invoice and no open PO for this vendor fits", "Procurement",
                         "Ask the requester for the PO, or treat as a non-PO invoice with a budget owner's approval"))
            return out, result
        else:
            out.append(V("PO_AMBIGUOUS", f"No PO number on invoice and {len(candidates)} open POs could fit: "
                                         f"{', '.join(candidates)}", "Procurement"))
            return out, result
    result["po_number"] = po
    po_lines = md.po_lines[po]
    if po_lines[0]["vendor_id"] != vendor["vendor_id"]:
        out.append(V("PO_VENDOR_MISMATCH", f"PO {po} belongs to vendor {po_lines[0]['vendor_id']}, "
                                           f"not {vendor['vendor_id']}", "Procurement"))
        return out, result
    if ex.get("currency") and po_lines[0]["currency"] != ex.get("currency"):
        out.append(V("CURRENCY_MISMATCH", f"Invoice in {ex.get('currency')}, PO in {po_lines[0]['currency']}"))
    tol = policy.price_tolerance_pct
    clean = True
    for il in ex.lines:
        pl, score = match_line(il, po_lines)
        row = {"invoice_line": il["description"], "qty": il["qty"], "unit_price": il["unit_price"]}
        if not pl:
            out.append(V("LINE_NOT_ON_PO", f"'{il['description']}' does not match any line on {po}", "Procurement"))
            clean = False
            result["lines"].append(row)
            continue
        billed = md.billed_qty(po, pl["line_no"])
        received = md.grn.get((po, pl["line_no"]), 0.0)
        remaining = pl["qty"] - billed
        row.update(po_line=pl["line_no"], po_qty=pl["qty"], po_price=pl["unit_price"], already_billed=billed,
                   received=received, match_score=round(score, 2))
        result["lines"].append(row)
        diff_pct = (il["unit_price"] - pl["unit_price"]) / pl["unit_price"] * 100 if pl["unit_price"] else 0
        if diff_pct > tol:
            clean = False
            out.append(V("PRICE_VARIANCE",
                         f"{pl['item_code']}: invoiced {il['unit_price']:,.2f} vs PO {pl['unit_price']:,.2f} "
                         f"(+{diff_pct:.1f}%, tolerance {tol:g}%). Extra cost "
                         f"{(il['unit_price'] - pl['unit_price']) * il['qty']:,.2f}",
                         "Buyer (procurement)", "Confirm an agreed price change and amend the PO, or ask the "
                                                "vendor for a credit note for the difference"))
        elif diff_pct > 0:
            out.append(I("PRICE_WITHIN_TOLERANCE", f"{pl['item_code']}: +{diff_pct:.1f}% within {tol:g}% tolerance"))
        if il["qty"] > remaining:
            clean = False
            out.append(V("PO_QTY_EXCEEDED",
                         f"{pl['item_code']}: PO qty {pl['qty']:g}, already billed {billed:g}, so {remaining:g} "
                         f"left; this invoice bills {il['qty']:g} ({il['qty'] - remaining:g} over)",
                         "Procurement", f"Check for a PO amendment. Otherwise approve only {remaining:g} and ask "
                                        f"for a credit note on the rest"))
        if billed + il["qty"] > received:
            clean = False
            out.append(V("GRN_SHORT",
                         f"{pl['item_code']}: received {received:g}, billed so far {billed:g} + {il['qty']:g} on this "
                         f"invoice = {billed + il['qty']:g}",
                         "Warehouse / requester", f"Confirm the receipt. If {received - billed:g} is right, pay "
                                                  f"for {max(received - billed, 0):g} and hold the rest"))
    if clean and ex.lines:
        out.append(I("THREE_WAY_OK", f"All {len(ex.lines)} line(s) match {po} on item, price and quantity, "
                                     f"and goods/services receipt covers the billed quantity"))
    return out, result


# ------------------------------------------------------------------ stage 8: policy
def check_policy(ex: Extraction, policy: Policy) -> list[Finding]:
    out = []
    total, cur, d = ex.get("total_amount"), ex.get("currency"), ex.get("invoice_date")
    limit = policy.approval_limit.get(cur)
    if total is not None and limit and total > limit:
        out.append(V("OVER_APPROVAL_LIMIT", f"{money(cur, total)} is above the auto-approval limit of {money(cur, limit)}",
                     "Finance manager", "Needs a second approval. Everything else is listed below for them"))
    if d:
        if d > policy.as_of:
            out.append(V("FUTURE_DATE", f"Invoice date {d} is after today ({policy.as_of})"))
        elif (policy.as_of - d).days > policy.max_invoice_age_days:
            out.append(V("STALE_INVOICE", f"Invoice is {(policy.as_of - d).days} days old", "AP",
                         "Check why it arrived late and whether GST input credit is still within the time limit"))
    return out
