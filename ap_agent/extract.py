"""Stage 1-2: read the document and pull out fields, each with a confidence score.

Order of preference:
  1. Text layer via pdfplumber (exact characters, high confidence).
  2. OCR via RapidOCR when a page has no text layer (scanned invoices). Lower starting confidence.
  3. Optional LLM pass (see llm.py) only for fields still missing or low confidence.

Confidence is not a model probability. It is a simple, explainable score:
  labelled match 0.95, pattern-only match 0.75, OCR multiplies by 0.90,
  and amounts move up or down depending on whether they reconcile with each other.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .config import BUYERS

LABELLED, PATTERN_ONLY, OCR_FACTOR = 0.95, 0.75, 0.90

AMT = r"(\d{1,3}(?:[.,]\d{2,3})*[.,]\d{2})"
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


@dataclass
class Field:
    value: object = None
    confidence: float = 0.0
    method: str = "missing"
    evidence: str = ""

    def as_dict(self):
        v = self.value.isoformat() if isinstance(self.value, date) else self.value
        return {"value": v, "confidence": round(self.confidence, 2), "method": self.method, "evidence": self.evidence}


@dataclass
class Document:
    path: Path
    text: str
    source: str            # "text" or "ocr"
    pages: int
    ocr_mean_conf: float | None = None
    line_conf: dict = field(default_factory=dict)   # OCR only: line text -> lowest token confidence


@dataclass
class Extraction:
    fields: dict = field(default_factory=dict)
    lines: list = field(default_factory=list)
    taxes: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def get(self, name):
        f = self.fields.get(name)
        return f.value if f else None

    def conf(self, name):
        f = self.fields.get(name)
        return f.confidence if f else 0.0


# ------------------------------------------------------------------ reading
_ocr_engine = None


def _ocr_page(page) -> tuple[str, float, dict]:
    """OCR one pdfium page and rebuild text lines from box positions."""
    global _ocr_engine
    import numpy as np
    if _ocr_engine is None:
        import logging
        from rapidocr import RapidOCR
        logging.getLogger("RapidOCR").setLevel(logging.ERROR)
        _ocr_engine = RapidOCR()
    img = page.render(scale=1.5).to_pil().convert("RGB")
    out = _ocr_engine(img)
    if not getattr(out, "txts", None):
        return "", 0.0, {}
    result = list(zip(out.boxes, out.txts, out.scores))
    boxes = sorted(((b[0][1], b[0][0], t, float(c)) for b, t, c in result), key=lambda r: (r[0], r[1]))
    rows, current, last_y = [], [], None
    for y, x, t, c in boxes:
        if last_y is not None and abs(y - last_y) > 8:
            rows.append(current)
            current = []
        current.append((x, t, c))
        last_y = y if last_y is None or not current[:-1] else (last_y + y) / 2
    rows.append(current)
    lines, line_conf = [], {}
    for r in rows:
        if not r:
            continue
        txt = " ".join(t for _, t, _ in sorted(r))
        lines.append(txt)
        line_conf[txt] = min(c for _, _, c in r)
    confs = [c for _, _, _, c in boxes]
    return "\n".join(lines), sum(confs) / len(confs), line_conf


def read_document(path: Path) -> Document:
    import pdfplumber
    path = Path(path)
    texts, needs_ocr = [], []
    with pdfplumber.open(path) as pdf:
        n = len(pdf.pages)
        for i, p in enumerate(pdf.pages):
            t = p.extract_text() or ""
            texts.append(t)
            if len(t.strip()) < 30:
                needs_ocr.append(i)
    if not needs_ocr:
        return Document(path, "\n".join(texts), "text", n)
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(path))
    confs, line_conf = [], {}
    for i in needs_ocr:
        t, c, lc = _ocr_page(pdf[i])
        texts[i] = t
        confs.append(c)
        line_conf.update(lc)
    return Document(path, "\n".join(texts), "ocr", n, round(sum(confs) / len(confs), 3) if confs else 0.0,
                    line_conf)


# ------------------------------------------------------------------ parsing helpers
def parse_amount(s: str) -> float | None:
    """Handles 1,74,640.00 (India), 174,640.00 (English) and 3.145,17 (German)."""
    if s is None:
        return None
    s = s.strip().replace(" ", "")
    m = re.fullmatch(r"(.*?)([.,])(\d{2})", s)
    if not m:
        try:
            return float(s.replace(",", ""))
        except ValueError:
            return None
    whole = re.sub(r"[.,]", "", m.group(1))
    try:
        return float(f"{whole}.{m.group(3)}")
    except ValueError:
        return None


def parse_date(s: str) -> date | None:
    s = s.strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    try:
        if m:
            return date(int(m[1]), int(m[2]), int(m[3]))
        m = re.match(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", s)
        if m:  # day first, the convention in India and the EU
            return date(int(m[3]), int(m[2]), int(m[1]))
        m = re.match(r"(\d{1,2})\s*([A-Za-z]{3})[a-z]*\.?\s*,?\s*(\d{4})", s)
        if m and m[2].lower() in MONTHS:
            return date(int(m[3]), MONTHS[m[2].lower()], int(m[1]))
    except ValueError:
        return None
    return None


# OCR often reads ":" as ";" or "." and drops spaces, so separators are loose on purpose
SEP = r"\s*[:;#.]*\s*"
CUR = r"(?:INR|EUR|Rs\.?|€)?"
DATE_PAT = r"(\d{4}-\d{2}-\d{2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4}|\d{1,2}\s*[A-Za-z]{3,9}\.?\s*,?\s*\d{4})"

LABELS = {
    "invoice_number": r"(?:Tax\s*Invoice\s*No\.?|Invoice\s*(?:No\.?|Number|#)|Bill\s*No\.?|Rechnungs?\s*nr\.?)" + SEP + r"([A-Z0-9][A-Z0-9/\-]{2,})",
    "invoice_date": r"(?:Invoice\s*Date|Bill\s*Date|Dated|Rechnungsdatum|(?<![A-Za-z])Date)" + SEP + DATE_PAT,
    "po_number": r"(?:PO\s*Number|Purchase\s*Order|Your\s*Order\s*No\.?|Order\s*Ref|Customer\s*PO|PO\s*Ref|(?<![A-Za-z])Ref)" + SEP + r"([A-Z]{2,}[A-Z0-9\-]*\d)",
    "service_period": r"Service\s*Period" + SEP + r"([A-Za-z0-9 \-]+?)\s*$",
}
PO_FORMAT = r"\b(KAV-(?:EU-)?PO-[0-9\-]*\d)\b"   # the buyer's own PO numbering, known in advance
TOTAL_LABELS = r"(?:Grand\s*Total|Total\s*Amount\s*Payable|Invoice\s*Total|Total\s*Due|Total\s*Amount|Amount\s*Payable|Total)"
NET_LABELS = r"(?:Taxable\s*Value|Taxable\s*Amount|Sub\s*-?\s*Total|Net\s*Amount|Amount)"
TAX_LINE = r"^(CGST|SGST|UTGST|IGST|VAT|USt|MwSt)[.:]?\s*@?\s*(\d+(?:[.,]\d+)?)\s*%\s*" + CUR + r"\s*" + AMT + r"\s*$"
GSTIN_LIKE = r"(?<![A-Z0-9])(\d{2}[A-Z]{5}\d{4}[A-Z][0-9A-Z]{3})"
LINE_ITEM = (r"^\s*(?:\d{1,2}\s+)?(?:([A-Z]{2}-[A-Z0-9.\-]+)|-)?\s*(.+?)\s+(\d+(?:\.\d+)?)\s*([A-Za-z]{2,6})\s*"
             + AMT + r"\s+" + AMT + r"\s*$")

BUYER_IDS = {b["tax_id"] for b in BUYERS.values()}
TITLE_WORDS = r"\s*(TAX\s*INVOICE|RECHNUNG\s*/\s*INVOICE|INVOICE|BILL)\s*$"


def _search(label_pat, text, flags=re.I | re.M):
    m = re.search(label_pat, text, flags)
    return (m.group(1), m.group(0)) if m else (None, None)


# ------------------------------------------------------------------ main extraction
def extract_fields(doc: Document) -> Extraction:
    text = doc.text
    ex = Extraction()
    F = ex.fields

    def ocr_factor(evidence):
        """For OCR, use the engine's own confidence on the line the value came from."""
        if doc.source != "ocr":
            return 1.0
        ev = (evidence or "").strip()
        for line, c in doc.line_conf.items():
            if ev and (ev in line or line in ev):
                return min(OCR_FACTOR, c)
        return OCR_FACTOR * 0.9

    def put(name, value, base, evidence):
        F[name] = Field(value, base * ocr_factor(evidence) if value is not None else 0.0,
                        ("ocr+" if doc.source == "ocr" else "") + ("label" if base == LABELLED else "pattern"),
                        (evidence or "").strip()[:120])

    # supplier name: first line, minus the document title
    first = next((l for l in text.splitlines() if l.strip()), "")
    name = re.sub(TITLE_WORDS, "", first, flags=re.I).strip()
    put("supplier_name", name or None, PATTERN_ONLY, first)

    # tax ids: buyer ids are known, so whatever else appears first is the supplier's
    compact = text.replace(" ", "")
    gstins = re.findall(GSTIN_LIKE, text)
    vats = re.findall(r"(?<![A-Z0-9])(DE\d{9}|NL\d{9}B\d{2}|FR[0-9A-Z]{2}\d{9}|IT\d{11}|ES[0-9A-Z]\d{7}[0-9A-Z])(?![0-9])", text)
    ids = gstins or vats
    supplier_ids = [i for i in ids if i not in BUYER_IDS]
    buyer_ids = [i for i in ids if i in BUYER_IDS]
    def line_of(token):
        return next((l for l in text.splitlines() if token and token in l), token or "")
    put("supplier_tax_id", supplier_ids[0] if supplier_ids else None, LABELLED, line_of(supplier_ids[0] if supplier_ids else ""))
    put("buyer_tax_id", buyer_ids[0] if buyer_ids else None, LABELLED, line_of(buyer_ids[0] if buyer_ids else ""))
    ex.notes.append(f"tax regime detected: {'GST' if gstins else 'VAT' if vats else 'unknown'}")
    F["tax_regime"] = Field("GST" if gstins else "VAT" if vats else None, 0.95 if ids else 0.0, "derived", "")

    v, ev = _search(LABELS["invoice_number"], text)
    put("invoice_number", v, LABELLED, ev)

    v, ev = _search(LABELS["invoice_date"], text)
    put("invoice_date", parse_date(v) if v else None, LABELLED, ev)

    v, ev = _search(LABELS["po_number"], text)
    if v:
        put("po_number", v.upper(), LABELLED, ev)
    else:
        v, ev = _search(PO_FORMAT, text)
        put("po_number", v, PATTERN_ONLY, ev)

    v, ev = _search(LABELS["service_period"], text)
    put("service_period", v, LABELLED, ev)

    # currency: count markers
    inr = len(re.findall(r"(?<![A-Z])INR(?![A-Z])|Rs\.|₹", text))
    eur = len(re.findall(r"(?<![A-Z])EUR(?![A-Z])|€", text))
    cur = "INR" if inr > eur else "EUR" if eur > inr else None
    put("currency", cur, LABELLED if max(inr, eur) >= 2 else PATTERN_ONLY, f"INR x{inr}, EUR x{eur}")

    # amounts and tax lines, line by line
    total = net = None
    for raw in text.splitlines():
        l = raw.strip()
        m = re.match(TAX_LINE, l, re.I)
        if m:
            kind = m[1].upper().rstrip(".")
            kind = "VAT" if kind in ("UST", "MWST") else kind
            ex.taxes.append({"type": kind, "rate": float(m[2].replace(",", ".")), "amount": parse_amount(m[3]),
                             "evidence": l})
            continue
        m = re.match(r"^" + TOTAL_LABELS + SEP + CUR + r"\s*" + AMT + r"\s*$", l, re.I)
        if m and total is None:
            total = (parse_amount(m[1]), l)
            continue
        m = re.match(r"^" + NET_LABELS + SEP + CUR + r"\s*" + AMT + r"\s*$", l, re.I)
        if m and net is None:
            net = (parse_amount(m[1]), l)
            continue
        m = re.match(LINE_ITEM, l)
        if m and not re.match(TOTAL_LABELS + "|" + NET_LABELS, l, re.I):
            ex.lines.append({"item_code": m[1], "description": m[2].strip(" -"), "qty": float(m[3]),
                             "unit": m[4], "unit_price": parse_amount(m[5]), "amount": parse_amount(m[6]),
                             "evidence": l})
    put("net_amount", net[0] if net else None, LABELLED, net[1] if net else "")
    put("total_amount", total[0] if total else None, LABELLED, total[1] if total else "")
    tax_sum = round(sum(t["amount"] or 0 for t in ex.taxes), 2) if ex.taxes else None
    if tax_sum is None and net and total:
        tax_sum = round(total[0] - net[0], 2)
        put("tax_amount", tax_sum, PATTERN_ONLY, "derived as total minus net")
    else:
        put("tax_amount", tax_sum, LABELLED, "; ".join(t["evidence"] for t in ex.taxes))

    # bank details
    iban = re.search(r"IBAN\s*:?\s*([A-Z]{2}\d{2}[A-Z0-9]{10,30}?)(?=\s|BIC|$)", text, re.M)
    acct = re.search(r"(?:A/c(?:No)?|AccountNumber|BankA/c|AccountNo)\.?:?(\d{6,20})", compact, re.I)
    v = iban[1] if iban else acct[1] if acct else None
    put("bank_account", v, LABELLED, (iban or acct)[0] if v else "")
    code = re.search(r"(?:IFSC(?:Code)?|BIC)\s*:?\s*([A-Z]{4}[A-Z0-9]{4,7})", compact)
    put("bank_code", code[1] if code else None, LABELLED, code[0] if code else "")

    rc = re.search(r"reverse\s*charge(?!\s*:\s*No)", text, re.I)
    F["reverse_charge_note"] = Field(bool(rc), 0.9, "pattern", rc[0] if rc else "")

    reconcile(ex)
    return ex


def reconcile(ex: Extraction, tol: float = 1.0) -> None:
    """Cross-check amounts against each other and adjust their confidence.

    If line items add up to net, and net plus tax equals total, three independent reads agree,
    which is stronger evidence than any single OCR score. If they disagree, confidence drops
    below the review threshold so a person looks at it.
    """
    net, tax, total = ex.get("net_amount"), ex.get("tax_amount"), ex.get("total_amount")
    checks = []
    if net is not None and tax is not None and total is not None:
        checks.append(abs(net + tax - total) <= tol)
    if ex.lines and net is not None:
        checks.append(abs(sum(l["amount"] or 0 for l in ex.lines) - net) <= tol)
    for l in ex.lines:
        if l["unit_price"] is not None and l["amount"] is not None:
            checks.append(abs(l["qty"] * l["unit_price"] - l["amount"]) <= tol)
    if not checks:
        return
    ok = all(checks)
    for name in ("net_amount", "tax_amount", "total_amount"):
        f = ex.fields.get(name)
        if f and f.value is not None:
            f.confidence = min(0.99, f.confidence + 0.07) if ok else f.confidence * 0.6
            f.method += "+reconciled" if ok else "+conflict"
    ex.notes.append("amounts reconcile (lines = net, net + tax = total)" if ok
                    else "amounts do NOT reconcile; confidence lowered")
