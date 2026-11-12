from datetime import date

from ap_agent import rules
from ap_agent.config import Policy
from ap_agent.extract import parse_amount, parse_date
from ap_agent.pipeline import decide
from tests.helpers import codes, make_ex, md

P = Policy(as_of=date(2026, 11, 12))


# ---------------- parsing
def test_amount_formats():
    assert parse_amount("1,74,640.00") == 174640.0      # Indian grouping
    assert parse_amount("3.145,17") == 3145.17          # German
    assert parse_amount("174,640.00") == 174640.0
    assert parse_amount("2.643.00") == 2643.0           # OCR read a comma as a dot


def test_dates_are_day_first():
    assert parse_date("05/11/2026") == date(2026, 11, 5)
    assert parse_date("3 Nov 2026") == date(2026, 11, 3)
    assert parse_date("03.11.2026") == date(2026, 11, 3)


# ---------------- vendor
def test_known_vendor_clean():
    v, f = rules.identify_vendor(make_ex(), md())
    assert v["vendor_id"] == "V001" and "BANK_MISMATCH" not in codes(f)


def test_bank_change_goes_to_review():
    v, f = rules.identify_vendor(make_ex(bank_account="99999999999"), md())
    assert "BANK_MISMATCH" in codes(f)


def test_unknown_vendor():
    v, f = rules.identify_vendor(make_ex(supplier_tax_id="29AAQFQ1209D1Z9", supplier_name="QuickFix"), md())
    assert v is None and "UNKNOWN_VENDOR" in codes(f)


# ---------------- completeness and arithmetic
def test_missing_invoice_number_rejects_on_text_pdf_but_reviews_on_scan():
    ex = make_ex(invoice_number=None)
    assert "MISSING_INVOICE_NUMBER" in codes(rules.check_completeness(ex, P, "text"))
    f = rules.check_completeness(ex, P, "ocr")
    assert "UNREADABLE_INVOICE_NUMBER" in codes(f) and all(x.severity == "review" for x in f)


def test_net_plus_tax_must_equal_total():
    assert "ARITHMETIC_MISMATCH" in codes(rules.check_completeness(make_ex(total_amount=31000.0), P))


def test_lines_must_sum_to_net():
    assert "LINES_DONT_SUM" in codes(rules.check_completeness(make_ex(net_amount=26000.0, tax_amount=4380.0,
                                                                      total_amount=30380.0), P))


def test_low_confidence_field_goes_to_review():
    assert "LOW_CONFIDENCE" in codes(rules.check_completeness(make_ex(conf={"total_amount": 0.6}), P))


# ---------------- GST
def test_intra_state_with_cgst_sgst_is_ok():
    f, _ = rules.check_tax(make_ex(), md().vendors["V001"], P)
    assert "GST_OK" in codes(f)


def test_intra_state_charging_igst_is_rejected():
    f, _ = rules.check_tax(make_ex(taxes=[{"type": "IGST", "rate": 18.0, "amount": 4635.0}]), md().vendors["V001"], P)
    assert "GST_REGIME_MISMATCH" in codes(f)


def test_inter_state_charging_cgst_is_rejected():
    ex = make_ex(supplier_tax_id="27AABFD2290P1Z5")
    f, _ = rules.check_tax(ex, md().vendors["V002"], P)
    assert "GST_REGIME_MISMATCH" in codes(f)


def test_wrong_tax_amount():
    ex = make_ex(taxes=[{"type": "CGST", "rate": 9.0, "amount": 2500.0}, {"type": "SGST", "rate": 9.0, "amount": 2500.0}])
    f, _ = rules.check_tax(ex, md().vendors["V001"], P)
    assert "TAX_CALC_ERROR" in codes(f)


def test_tds_is_noted_not_blocking():
    ex = make_ex(supplier_tax_id="36AAKFN5521Q1ZP", net_amount=38500.0, tax_amount=6930.0, total_amount=45430.0,
                 taxes=[{"type": "IGST", "rate": 18.0, "amount": 6930.0}])
    f, tds = rules.check_tax(ex, md().vendors["V003"], P)
    assert tds["tds_amount"] == 770.0 and all(x.severity == "info" for x in f if x.code == "TDS")


# ---------------- EU VAT
def test_cross_border_eu_vat_charged_is_rejected():
    ex = make_ex(tax_regime="VAT", supplier_tax_id="NL853112907B01", buyer_tax_id="DE318273645", currency="EUR",
                 net_amount=2600.0, tax_amount=546.0, total_amount=3146.0,
                 taxes=[{"type": "VAT", "rate": 21.0, "amount": 546.0}])
    assert "EU_REVERSE_CHARGE" in codes(rules.check_tax(ex, None, P)[0])


def test_cross_border_reverse_charge_ok():
    ex = make_ex(tax_regime="VAT", supplier_tax_id="NL853112907B01", buyer_tax_id="DE318273645", currency="EUR",
                 net_amount=2600.0, tax_amount=0.0, total_amount=2600.0, taxes=[], reverse_charge_note=True)
    assert "VAT_OK" in codes(rules.check_tax(ex, None, P)[0])


# ---------------- duplicates
def test_exact_duplicate_after_normalising_number():
    m = md()
    ex = make_ex(supplier_tax_id="36AAKFN5521Q1ZP", invoice_number="ncs-inv-2026-88", total_amount=45430.0)
    assert "DUPLICATE_EXACT" in codes(rules.check_duplicates(ex, m.vendors["V003"], m, P))


def test_reissued_invoice_is_suspected_duplicate():
    m = md()
    ex = make_ex(invoice_number="MFS-1043", invoice_date=date(2026, 11, 3), total_amount=47200.0,
                 po_number="KAV-PO-2026-1108", service_period="Oct2026")
    assert "DUPLICATE_SUSPECTED" in codes(rules.check_duplicates(ex, m.vendors["V005"], m, P))


def test_next_month_same_amount_is_not_a_duplicate():
    m = md()
    ex = make_ex(invoice_number="MFS-1099", invoice_date=date(2026, 11, 30), total_amount=47200.0,
                 po_number="KAV-PO-2026-1108", service_period="Nov 2026")
    assert "DUPLICATE_SUSPECTED" not in codes(rules.check_duplicates(ex, m.vendors["V005"], m, P))


# ---------------- 3-way match
def test_clean_three_way_match():
    f, r = rules.three_way_match(make_ex(), md().vendors["V001"], md(), P)
    assert "THREE_WAY_OK" in codes(f) and r["po_number"] == "KAV-PO-2026-1101"


def test_price_over_tolerance():
    lines = [{"item_code": "PK-5PLY-450", "description": "box", "qty": 500, "unit": "Nos", "unit_price": 44.0,
              "amount": 22000.0}]
    f, _ = rules.three_way_match(make_ex(lines=lines), md().vendors["V001"], md(), P)
    assert "PRICE_VARIANCE" in codes(f)


def test_price_within_tolerance_is_info_only():
    lines = [{"item_code": "PK-5PLY-450", "description": "box", "qty": 500, "unit": "Nos", "unit_price": 42.5,
              "amount": 21250.0}]
    f, _ = rules.three_way_match(make_ex(lines=lines), md().vendors["V001"], md(), P)
    assert "PRICE_WITHIN_TOLERANCE" in codes(f) and "PRICE_VARIANCE" not in codes(f)


def test_split_po_over_billing():
    lines = [{"item_code": "PK-CTN-STD", "description": "carton", "qty": 700, "unit": "Nos", "unit_price": 18.0,
              "amount": 12600.0}]
    f, _ = rules.three_way_match(make_ex(lines=lines, po_number="KAV-PO-2026-1104"), md().vendors["V001"], md(), P)
    assert "PO_QTY_EXCEEDED" in codes(f)


def test_billed_more_than_received():
    lines = [{"item_code": "EL-TRAY-300", "description": "tray", "qty": 300, "unit": "Nos", "unit_price": 640.0,
              "amount": 192000.0}]
    f, _ = rules.three_way_match(make_ex(lines=lines, po_number="KAV-PO-2026-1105", supplier_tax_id="27AABFD2290P1Z5"),
                                 md().vendors["V002"], md(), P)
    assert "GRN_SHORT" in codes(f)


def test_po_inferred_when_exactly_one_fits():
    lines = [{"item_code": "SV-CLOUD-M", "description": "Managed cloud hosting - monthly", "qty": 1, "unit": "Month",
              "unit_price": 38500.0, "amount": 38500.0}]
    f, r = rules.three_way_match(make_ex(lines=lines, po_number=None), md().vendors["V003"], md(), P)
    assert "PO_INFERRED" in codes(f) and r["po_number"] == "KAV-PO-2026-1106"


def test_po_belonging_to_another_vendor():
    f, _ = rules.three_way_match(make_ex(po_number="KAV-PO-2026-1102"), md().vendors["V001"], md(), P)
    assert "PO_VENDOR_MISMATCH" in codes(f)


# ---------------- policy and decision
def test_over_approval_limit():
    assert "OVER_APPROVAL_LIMIT" in codes(rules.check_policy(make_ex(total_amount=708000.0), P))


def test_future_and_stale_dates():
    assert "FUTURE_DATE" in codes(rules.check_policy(make_ex(invoice_date=date(2026, 12, 1)), P))
    assert "STALE_INVOICE" in codes(rules.check_policy(make_ex(invoice_date=date(2026, 1, 1)), P))


def test_reject_beats_review_beats_approve():
    r, v, i = rules.R("A", "x"), rules.V("B", "y"), rules.I("C", "z")
    assert decide([i])["route"] == "AUTO_APPROVE"
    assert decide([i, v])["route"] == "NEEDS_REVIEW"
    d = decide([i, v, r])
    assert d["route"] == "REJECT" and d["also_noted"][0]["code"] == "B"
