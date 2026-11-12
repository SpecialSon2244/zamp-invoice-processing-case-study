"""Generate the SYNTHETIC test set: master data (vendors, POs, GRNs, AP ledger),
18 invoice PDFs with deliberate edge cases, and a ground-truth file.

Every company, GSTIN, VAT ID, bank account and amount here is made up.
GSTINs are built with a valid checksum so the checksum rule can be tested honestly.

Run: python scripts/generate_samples.py
"""
import csv
import io
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from ap_agent.config import BUYERS
from ap_agent.taxids import make_gstin

DATA = ROOT / "data"
INBOX = DATA / "inbox"
SYN = "SYNTHETIC TEST DATA - fictional company, not a real invoice"

# ---------------------------------------------------------------- vendor master
VENDORS = [
    dict(vendor_id="V001", name="Sri Lakshmi Packaging Pvt Ltd", country="IN", state_code="29",
         city="Peenya, Bengaluru", tax_id=make_gstin("29", "AAFCS7731K"), pan="AAFCS7731K",
         bank_account="50200041187723", bank_code="HDFC0001234", currency="INR",
         tds_section="", tds_rate=0, status="active"),
    dict(vendor_id="V002", name="Deccan Electricals & Components", country="IN", state_code="27",
         city="Bhosari, Pune", tax_id=make_gstin("27", "AABFD2290P"), pan="AABFD2290P",
         bank_account="914020038812201", bank_code="UTIB0000412", currency="INR",
         tds_section="", tds_rate=0, status="active"),
    dict(vendor_id="V003", name="Nimbus Cloud Services LLP", country="IN", state_code="36",
         city="Madhapur, Hyderabad", tax_id=make_gstin("36", "AAKFN5521Q"), pan="AAKFN5521Q",
         bank_account="0391102000017745", bank_code="ICIC0000391", currency="INR",
         tds_section="194J", tds_rate=2.0, status="active"),
    dict(vendor_id="V004", name="Coastal Freight Movers", country="IN", state_code="33",
         city="Ambattur, Chennai", tax_id=make_gstin("33", "AAJFC6612R"), pan="AAJFC6612R",
         bank_account="6012345678", bank_code="IDIB000A012", currency="INR",
         tds_section="194C", tds_rate=2.0, status="active"),
    dict(vendor_id="V005", name="Malnad Facility Services", country="IN", state_code="29",
         city="Hebbal, Mysuru", tax_id=make_gstin("29", "AAGFM3384L"), pan="AAGFM3384L",
         bank_account="38291045562", bank_code="SBIN0040213", currency="INR",
         tds_section="194C", tds_rate=2.0, status="active"),
    dict(vendor_id="V101", name="Rheinwerk Industrietechnik GmbH", country="DE", state_code="",
         city="50667 Koeln", tax_id="DE274915538", pan="",
         bank_account="DE44370400440532013000", bank_code="COBADEFFXXX", currency="EUR",
         tds_section="", tds_rate=0, status="active"),
    dict(vendor_id="V102", name="Van Dijk Precision B.V.", country="NL", state_code="",
         city="5611 Eindhoven", tax_id="NL853112907B01", pan="",
         bank_account="NL91ABNA0417164300", bank_code="ABNANL2A", currency="EUR",
         tds_section="", tds_rate=0, status="active"),
]
V = {v["vendor_id"]: v for v in VENDORS}
BUYER_IN, BUYER_DE = BUYERS["IN"], BUYERS["DE"]

# ---------------------------------------------------------------- purchase orders
# (po, vendor, entity, line, item_code, description, qty, unit_price, currency)
PO_LINES = [
    ("KAV-PO-2026-1101", "V001", "IN", 1, "PK-5PLY-450", "Corrugated box 5-ply 450x350x300", 500, 42.00, "INR"),
    ("KAV-PO-2026-1101", "V001", "IN", 2, "PK-FOAM-IN", "EPE foam insert set", 500, 9.50, "INR"),
    ("KAV-PO-2026-1102", "V002", "IN", 1, "EL-MCB-32A", "MCB 32A double pole", 200, 310.00, "INR"),
    ("KAV-PO-2026-1102", "V002", "IN", 2, "EL-CU-2.5", "Copper wire 2.5 sq mm (90 m coil)", 40, 2150.00, "INR"),
    ("KAV-PO-2026-1103", "V002", "IN", 1, "EL-LED-DRV", "LED driver 36W constant current", 1000, 95.00, "INR"),
    ("KAV-PO-2026-1104", "V001", "IN", 1, "PK-CTN-STD", "Shipper carton standard", 2000, 18.00, "INR"),
    ("KAV-PO-2026-1105", "V002", "IN", 1, "EL-TRAY-300", "Perforated cable tray 300 mm", 300, 640.00, "INR"),
    ("KAV-PO-2026-1106", "V003", "IN", 1, "SV-CLOUD-M", "Managed cloud hosting - monthly", 12, 38500.00, "INR"),
    ("KAV-PO-2026-1107", "V004", "IN", 1, "LG-FTL-BLR-CHN", "Full truck load Bengaluru to Chennai", 6, 21500.00, "INR"),
    ("KAV-PO-2026-1108", "V005", "IN", 1, "SV-HK-MONTH", "Housekeeping services - monthly", 12, 40000.00, "INR"),
    ("KAV-PO-2026-1109", "V002", "IN", 1, "EL-PANEL-LT", "LT distribution panel 400A", 4, 150000.00, "INR"),
    ("KAV-PO-2026-1110", "V005", "IN", 1, "SV-PEST-Q", "Pest control - quarterly", 4, 12500.00, "INR"),
    ("KAV-EU-PO-0412", "V101", "DE", 1, "RW-BRG-6205", "Deep groove ball bearing 6205-2RS", 120, 18.40, "EUR"),
    ("KAV-EU-PO-0412", "V101", "DE", 2, "RW-SEAL-KIT", "Shaft seal kit", 60, 7.25, "EUR"),
    ("KAV-EU-PO-0418", "V101", "DE", 1, "RW-GBX-40", "Worm gearbox ratio 40:1", 30, 45.00, "EUR"),
    ("KAV-EU-PO-0420", "V102", "DE", 1, "VD-SHAFT-20", "Precision ground shaft 20 mm", 80, 32.50, "EUR"),
]

# GRN: goods/services received against each PO line (po, line, qty, grn_no, date)
GRNS = [
    ("KAV-PO-2026-1101", 1, 500, "GRN-26-3301", "2026-11-03"),
    ("KAV-PO-2026-1101", 2, 500, "GRN-26-3301", "2026-11-03"),
    ("KAV-PO-2026-1102", 1, 200, "GRN-26-3305", "2026-11-04"),
    ("KAV-PO-2026-1102", 2, 40, "GRN-26-3305", "2026-11-04"),
    ("KAV-PO-2026-1103", 1, 600, "GRN-26-3190", "2026-10-20"),
    ("KAV-PO-2026-1103", 1, 400, "GRN-26-3312", "2026-11-05"),
    ("KAV-PO-2026-1104", 1, 2000, "GRN-26-3201", "2026-10-22"),
    ("KAV-PO-2026-1105", 1, 270, "GRN-26-3318", "2026-11-06"),
    ("KAV-PO-2026-1106", 1, 12, "SES-26-0711", "2026-11-01"),
    ("KAV-PO-2026-1107", 1, 6, "GRN-26-3320", "2026-11-07"),
    ("KAV-PO-2026-1108", 1, 11, "SES-26-0715", "2026-11-01"),
    ("KAV-PO-2026-1109", 1, 4, "GRN-26-3324", "2026-11-08"),
    ("KAV-PO-2026-1110", 1, 4, "SES-26-0720", "2026-11-02"),
    ("KAV-EU-PO-0412", 1, 120, "WE-26-0218", "2026-11-02"),
    ("KAV-EU-PO-0412", 2, 60, "WE-26-0218", "2026-11-02"),
    ("KAV-EU-PO-0418", 1, 30, "WE-26-0223", "2026-11-04"),
    ("KAV-EU-PO-0420", 1, 80, "WE-26-0225", "2026-11-05"),
]

# AP ledger: invoices already booked before this batch (used for duplicates and PO consumption)
LEDGER = [
    dict(vendor_id="V002", invoice_number="DEC/2026/1120", invoice_date="2026-10-21", currency="INR",
         total=67260.00, po_number="KAV-PO-2026-1103", billed_lines="1:600", service_period="", status="paid"),
    dict(vendor_id="V001", invoice_number="SLP/26-27/0391", invoice_date="2026-10-23", currency="INR",
         total=31860.00, po_number="KAV-PO-2026-1104", billed_lines="1:1500", service_period="", status="paid"),
    dict(vendor_id="V003", invoice_number="NCS/INV/2026/0088", invoice_date="2026-10-01", currency="INR",
         total=45430.00, po_number="KAV-PO-2026-1106", billed_lines="1:1", service_period="Oct 2026", status="paid"),
    dict(vendor_id="V005", invoice_number="MFS-1042", invoice_date="2026-10-31", currency="INR",
         total=47200.00, po_number="KAV-PO-2026-1108", billed_lines="1:1", service_period="Oct 2026", status="approved"),
    dict(vendor_id="V003", invoice_number="NCS/INV/2026/0061", invoice_date="2026-09-01", currency="INR",
         total=45430.00, po_number="KAV-PO-2026-1106", billed_lines="1:1", service_period="Sep 2026", status="paid"),
    dict(vendor_id="V005", invoice_number="MFS-0987", invoice_date="2026-09-30", currency="INR",
         total=47200.00, po_number="KAV-PO-2026-1108", billed_lines="1:1", service_period="Sep 2026", status="paid"),
]
# Note: before this batch PO-1106 had 10 months billed and PO-1108 10 months; the ledger lists only the
# recent ones. The consumed quantities below make the PO arithmetic right.
PRIOR_CONSUMPTION_NOTE = {"KAV-PO-2026-1106": 10, "KAV-PO-2026-1108": 10}


# ---------------------------------------------------------------- number formats
def fmt_in(x: float) -> str:
    """Indian digit grouping: 1,74,640.00"""
    neg = x < 0
    s = f"{abs(x):.2f}"
    whole, dec = s.split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts) + "," + tail
    return ("-" if neg else "") + whole + "." + dec


def fmt_de(x: float) -> str:
    """German format: 3.145,17"""
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_en(x: float) -> str:
    return f"{x:,.2f}"


# ---------------------------------------------------------------- invoice specs
def line(code, desc, qty, price, unit="Nos"):
    return dict(item_code=code, description=desc, qty=qty, unit_price=price, unit=unit, amount=round(qty * price, 2))


def gst_invoice(file, vendor_id, number, date_str, po, lines, regime=None, rate=18.0, supplier_gstin=None,
                bank=None, template="A", period="", expected_route="", edge_case="", reasons=None,
                extra_note="", scanned=False, show_number=True, hsn="", buyer_gstin=None):
    v = V[vendor_id]
    net = round(sum(l["amount"] for l in lines), 2)
    supplier_state = (supplier_gstin or v["tax_id"])[:2]
    natural = "intra" if supplier_state == BUYER_IN["tax_id"][:2] else "inter"
    regime = regime or natural
    if regime == "intra":
        cgst = sgst = round(net * rate / 200, 2)
        taxes = [("CGST", rate / 2, cgst), ("SGST", rate / 2, sgst)]
    else:
        taxes = [("IGST", rate, round(net * rate / 100, 2))]
    tax = round(sum(t[2] for t in taxes), 2)
    return dict(file=file, kind="GST", vendor_id=vendor_id, vendor_name=v["name"], city=v["city"],
                supplier_tax_id=supplier_gstin or v["tax_id"], buyer=BUYER_IN, buyer_tax_id=buyer_gstin or BUYER_IN["tax_id"],
                invoice_number=number if show_number else None, printed_number=show_number, invoice_date=date_str,
                po_number=po, lines=lines, taxes=taxes, net=net, tax=tax, total=round(net + tax, 2),
                currency="INR", bank_account=bank[0] if bank else v["bank_account"],
                bank_code=bank[1] if bank else v["bank_code"], template=template, service_period=period,
                expected_route=expected_route, edge_case=edge_case, expected_reasons=reasons or [],
                note=extra_note, scanned=scanned)


def eu_invoice(file, vendor_id, number, date_str, po, lines, vat_rate, reverse_charge=False, template="EU",
               expected_route="", edge_case="", reasons=None, num_style="de"):
    v = V[vendor_id]
    net = round(sum(l["amount"] for l in lines), 2)
    vat = round(net * vat_rate / 100, 2)
    return dict(file=file, kind="VAT", vendor_id=vendor_id, vendor_name=v["name"], city=v["city"],
                supplier_tax_id=v["tax_id"], buyer=BUYER_DE, buyer_tax_id=BUYER_DE["tax_id"],
                invoice_number=number, printed_number=True, invoice_date=date_str, po_number=po, lines=lines,
                taxes=[("VAT", vat_rate, vat)], net=net, tax=vat, total=round(net + vat, 2), currency="EUR",
                bank_account=v["bank_account"], bank_code=v["bank_code"], template=template, service_period="",
                expected_route=expected_route, edge_case=edge_case, expected_reasons=reasons or [],
                reverse_charge=reverse_charge, num_style=num_style, note="", scanned=False)


INVOICES = [
    gst_invoice("01_sri_lakshmi_happy_intrastate.pdf", "V001", "SLP/26-27/0418", "2026-11-04", "KAV-PO-2026-1101",
                [line("PK-5PLY-450", "Corrugated box 5-ply 450x350x300", 500, 42.00),
                 line("PK-FOAM-IN", "EPE foam insert set", 500, 9.50, "Set")],
                expected_route="AUTO_APPROVE", edge_case="Happy path: Karnataka vendor, CGST + SGST, clean 3-way match"),
    gst_invoice("02_deccan_happy_interstate.pdf", "V002", "DEC/2026/1187", "2026-11-05", "KAV-PO-2026-1102",
                [line("EL-MCB-32A", "MCB 32A double pole", 200, 310.00),
                 line("EL-CU-2.5", "Copper wire 2.5 sq mm (90 m coil)", 40, 2150.00, "Coil")],
                template="B", expected_route="AUTO_APPROVE", edge_case="Happy path: Maharashtra vendor, IGST, clean 3-way match"),
    eu_invoice("03_rheinwerk_happy_de.pdf", "V101", "RW-2026-00731", "2026-11-03", "KAV-EU-PO-0412",
               [line("RW-BRG-6205", "Deep groove ball bearing 6205-2RS", 120, 18.40, "Stk"),
                line("RW-SEAL-KIT", "Shaft seal kit", 60, 7.25, "Stk")], 19.0,
               expected_route="AUTO_APPROVE", edge_case="Happy path: German vendor, 19% VAT, German number format"),
    gst_invoice("04_deccan_split_po_final_part.pdf", "V002", "DEC/2026/1201", "2026-11-06", "KAV-PO-2026-1103",
                [line("EL-LED-DRV", "LED driver 36W constant current", 400, 95.00)], template="B",
                expected_route="AUTO_APPROVE",
                edge_case="Split PO: second invoice for the remaining 400 of 1000 units (600 already billed)"),
    gst_invoice("05_sri_lakshmi_split_po_overbilled.pdf", "V001", "SLP/26-27/0433", "2026-11-07", "KAV-PO-2026-1104",
                [line("PK-CTN-STD", "Shipper carton standard", 700, 18.00)],
                expected_route="NEEDS_REVIEW", reasons=["PO_QTY_EXCEEDED"],
                edge_case="Split PO over-billing: 1500 of 2000 already billed, this invoice bills 700 more"),
    gst_invoice("06_nimbus_exact_duplicate.pdf", "V003", "NCS/INV/2026/0088", "2026-10-01", "KAV-PO-2026-1106",
                [line("SV-CLOUD-M", "Managed cloud hosting - monthly", 1, 38500.00, "Month")], template="C",
                period="Oct 2026", expected_route="REJECT", reasons=["DUPLICATE_EXACT"],
                edge_case="Exact duplicate: same vendor and invoice number already paid"),
    gst_invoice("07_malnad_near_duplicate_reissued.pdf", "V005", "MFS-1043", "2026-11-03", "KAV-PO-2026-1108",
                [line("SV-HK-MONTH", "Housekeeping services - monthly", 1, 40000.00, "Month")], template="C",
                period="Oct 2026", expected_route="NEEDS_REVIEW", reasons=["DUPLICATE_SUSPECTED"],
                edge_case="Near-duplicate: vendor re-issued October under a new number (MFS-1042 already approved)"),
    gst_invoice("08_malnad_wrong_tax_regime.pdf", "V005", "MFS-1051", "2026-11-05", "KAV-PO-2026-1110",
                [line("SV-PEST-Q", "Pest control - quarterly", 1, 12500.00, "Visit")], regime="inter",
                template="C", period="Q3 FY26-27", expected_route="REJECT", reasons=["GST_REGIME_MISMATCH"],
                edge_case="Karnataka vendor billing a Karnataka buyer with IGST instead of CGST + SGST"),
    gst_invoice("09_coastal_invalid_gstin.pdf", "V004", "CFM/2026/552", "2026-11-07", "KAV-PO-2026-1107",
                [line("LG-FTL-BLR-CHN", "Full truck load Bengaluru to Chennai", 2, 21500.00, "Trip")],
                supplier_gstin=V["V004"]["tax_id"][:14] + ("A" if V["V004"]["tax_id"][14] != "A" else "B"),
                rate=5.0, template="B", expected_route="REJECT", reasons=["GSTIN_INVALID"],
                edge_case="Supplier GSTIN typo: fails the checksum, so input tax credit cannot be claimed"),
    gst_invoice("10_coastal_bank_details_changed.pdf", "V004", "CFM/2026/561", "2026-11-08", "KAV-PO-2026-1107",
                [line("LG-FTL-BLR-CHN", "Full truck load Bengaluru to Chennai", 3, 21500.00, "Trip")],
                rate=5.0, bank=("77120055410983", "KKBK0008811"), template="B",
                expected_route="NEEDS_REVIEW", reasons=["BANK_MISMATCH"],
                edge_case="Bank account on invoice differs from vendor master (classic payment fraud pattern)"),
    gst_invoice("11_deccan_short_receipt.pdf", "V002", "DEC/2026/1209", "2026-11-07", "KAV-PO-2026-1105",
                [line("EL-TRAY-300", "Perforated cable tray 300 mm", 300, 640.00)], template="B",
                expected_route="NEEDS_REVIEW", reasons=["GRN_SHORT"],
                edge_case="3-way mismatch: invoiced 300 trays, warehouse received 270"),
    eu_invoice("12_rheinwerk_price_variance.pdf", "V101", "RW-2026-00755", "2026-11-06", "KAV-EU-PO-0418",
               [line("RW-GBX-40", "Worm gearbox ratio 40:1", 30, 48.60, "Stk")], 19.0,
               expected_route="NEEDS_REVIEW", reasons=["PRICE_VARIANCE"],
               edge_case="Unit price 8% above PO price (tolerance is 2%)"),
    gst_invoice("13_nimbus_no_po_inferred.pdf", "V003", "NCS/INV/2026/0112", "2026-11-01", None,
                [line("SV-CLOUD-M", "Managed cloud hosting - monthly", 1, 38500.00, "Month")], template="C",
                period="Nov 2026", expected_route="AUTO_APPROVE", reasons=["PO_INFERRED", "TDS"],
                edge_case="No PO number printed: process infers the only open PO that fits; TDS 194J noted"),
    gst_invoice("15_malnad_messy_no_invoice_number.pdf", "V005", "MFS-1055", "2026-11-09", "KAV-PO-2026-1108",
                [line("", "Housekeeping services Nov 2026 - lump sum as per contract", 1, 40000.00, "LS")],
                template="D", period="Nov 2026", show_number=False, expected_route="REJECT",
                reasons=["MISSING_INVOICE_NUMBER"],
                edge_case="Messy bill: no invoice number, bundled lump-sum line, different labels"),
    eu_invoice("16_vandijk_vat_instead_of_reverse_charge.pdf", "V102", "VDP-26-1187", "2026-11-06", "KAV-EU-PO-0420",
               [line("VD-SHAFT-20", "Precision ground shaft 20 mm", 80, 32.50, "pcs")], 21.0,
               template="EU2", num_style="en", expected_route="REJECT", reasons=["EU_REVERSE_CHARGE"],
               edge_case="Dutch vendor charged 21% NL VAT on a B2B sale to Germany; should be reverse charge"),
    dict(gst_invoice("17_unknown_vendor.pdf", "V001", "QFT-2026-77", "2026-11-09", None,
                     [line("", "Office chairs ergonomic", 10, 6500.00)], template="D",
                     expected_route="NEEDS_REVIEW", reasons=["UNKNOWN_VENDOR"],
                     edge_case="Vendor not in vendor master (no onboarding, no PO)"),
         vendor_id="", vendor_name="QuickFix Office Traders", city="KR Puram, Bengaluru",
         supplier_tax_id=make_gstin("29", "AAQFQ1209D"), bank_account="1100223344", bank_code="CNRB0001122"),
    gst_invoice("18_deccan_over_approval_limit.pdf", "V002", "DEC/2026/1215", "2026-11-09", "KAV-PO-2026-1109",
                [line("EL-PANEL-LT", "LT distribution panel 400A", 4, 150000.00)], template="B",
                expected_route="NEEDS_REVIEW", reasons=["OVER_APPROVAL_LIMIT"],
                edge_case="Everything matches, but INR 7.08 lakh is above the INR 5 lakh auto-approval limit"),
]

INVOICES.insert(13, dict(gst_invoice("14_malnad_scanned_image_only.pdf", "V005", "MFS-1058", "2026-11-10",
                                "KAV-PO-2026-1110",
                                [line("SV-PEST-Q", "Pest control - quarterly", 1, 12500.00, "Visit")],
                                template="C", period="Q3 FY26-27", scanned=True,
                                expected_route="AUTO_APPROVE", reasons=["OCR"],
                                edge_case="Scanned image, no text layer: OCR reads it; amounts must reconcile before auto-approval")))


# ---------------------------------------------------------------- PDF drawing
def money(inv, x):
    if inv["currency"] == "INR":
        return fmt_in(x)
    return fmt_de(x) if inv.get("num_style", "de") == "de" else fmt_en(x)


def date_print(inv):
    y, m, d = inv["invoice_date"].split("-")
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    t = inv["template"]
    if t == "A":
        return f"{d}-{m}-{y}"
    if t == "B":
        return f"{d}/{m}/{y}"
    if t == "C":
        return f"{int(d)} {months[int(m)-1]} {y}"
    if t == "D":
        return f"{d}.{m}.{y}"
    if t == "EU":
        return f"{d}.{m}.{y}"
    return f"{y}-{m}-{d}"


LABELS = {
    "A": dict(title="TAX INVOICE", num="Invoice No", date="Invoice Date", po="PO Number", net="Taxable Value",
              total="Grand Total", bank="A/c No", code="IFSC"),
    "B": dict(title="TAX INVOICE", num="Invoice #", date="Date", po="Purchase Order", net="Sub Total",
              total="Total Amount Payable", bank="Account Number", code="IFSC Code"),
    "C": dict(title="TAX INVOICE", num="Tax Invoice No.", date="Dated", po="Your Order No.", net="Taxable Amount",
              total="Invoice Total", bank="Bank A/c", code="IFSC"),
    "D": dict(title="BILL", num="Bill No", date="Bill Date", po="Ref", net="Amount", total="Total Due",
              bank="A/c", code="IFSC"),
    "EU": dict(title="RECHNUNG / INVOICE", num="Invoice No", date="Invoice Date", po="Order Ref", net="Net Amount",
               total="Total Amount", bank="IBAN", code="BIC"),
    "EU2": dict(title="INVOICE", num="Invoice Number", date="Invoice Date", po="Customer PO", net="Subtotal",
                total="Total Due", bank="IBAN", code="BIC"),
}


def draw_invoice(inv, path_or_buf):
    c = canvas.Canvas(path_or_buf, pagesize=A4)
    W, H = A4
    L = LABELS[inv["template"]]
    c.setTitle(f"{inv['vendor_name']} invoice (synthetic)")
    # synthetic watermark
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.grey)
    c.drawString(15 * mm, 8 * mm, SYN)
    c.setFillColor(colors.black)

    y = H - 20 * mm
    c.setFont("Helvetica-Bold", 15)
    c.drawString(15 * mm, y, inv["vendor_name"])
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(W - 15 * mm, y, L["title"])
    c.setFont("Helvetica", 9)
    y -= 6 * mm
    c.drawString(15 * mm, y, inv["city"] + (", India" if inv["kind"] == "GST" else ""))
    y -= 5 * mm
    tax_label = "GSTIN" if inv["kind"] == "GST" else "VAT ID"
    c.drawString(15 * mm, y, f"{tax_label}: {inv['supplier_tax_id']}")
    if inv["kind"] == "GST" and inv["vendor_id"]:
        y -= 5 * mm
        c.drawString(15 * mm, y, f"PAN: {inv['supplier_tax_id'][2:12]}")

    # header block right
    ry = H - 28 * mm
    rows = []
    if inv["printed_number"]:
        rows.append((L["num"], inv["invoice_number"]))
    rows.append((L["date"], date_print(inv)))
    if inv["po_number"]:
        rows.append((L["po"], inv["po_number"]))
    if inv["service_period"]:
        rows.append(("Service Period", inv["service_period"]))
    if inv["kind"] == "GST":
        rows.append(("Place of Supply", "Karnataka (29)"))
    for k, val in rows:
        c.setFont("Helvetica", 9)
        c.drawRightString(W - 15 * mm, ry, f"{k}: {val}")
        ry -= 5 * mm

    # bill to
    y = H - 62 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(15 * mm, y, "Bill To:")
    c.setFont("Helvetica", 9)
    y -= 5 * mm
    c.drawString(15 * mm, y, inv["buyer"]["name"])
    y -= 5 * mm
    c.drawString(15 * mm, y, "Whitefield, Bengaluru 560066, Karnataka" if inv["kind"] == "GST"
                 else "Schlesische Str. 28, 10997 Berlin, Germany")
    y -= 5 * mm
    c.drawString(15 * mm, y, f"{tax_label}: {inv['buyer_tax_id']}")

    # table
    y -= 12 * mm
    c.setFont("Helvetica-Bold", 9)
    cols = [15, 30, 62, 140, 160, 182]
    heads = ["#", "Item Code", "Description", "Qty", "Rate", "Amount"]
    for x, h in zip(cols, heads):
        if h in ("Qty", "Rate", "Amount"):
            c.drawRightString((x + 13) * mm if h != "Amount" else (W - 15 * mm), y, h)
        else:
            c.drawString(x * mm, y, h)
    c.line(15 * mm, y - 2 * mm, W - 15 * mm, y - 2 * mm)
    c.setFont("Helvetica", 9)
    for i, ln in enumerate(inv["lines"], 1):
        y -= 7 * mm
        c.drawString(15 * mm, y, str(i))
        c.drawString(30 * mm, y, ln["item_code"] or "-")
        c.drawString(62 * mm, y, ln["description"][:44])
        c.drawRightString(153 * mm, y, f"{ln['qty']:g} {ln['unit']}")
        c.drawRightString(173 * mm, y, money(inv, ln["unit_price"]))
        c.drawRightString(W - 15 * mm, y, money(inv, ln["amount"]))
    y -= 4 * mm
    c.line(15 * mm, y, W - 15 * mm, y)

    # totals
    y -= 7 * mm
    cur = inv["currency"]
    def tot(label, val, bold=False):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 10 if bold else 9)
        c.drawRightString(160 * mm, y, label)
        c.drawRightString(W - 15 * mm, y, f"{cur} {money(inv, val)}")
        y -= 6 * mm
    tot(L["net"], inv["net"])
    for name, rate, amt in inv["taxes"]:
        tot(f"{name} @ {rate:g}%", amt)
    tot(L["total"], inv["total"], bold=True)

    y -= 6 * mm
    c.setFont("Helvetica", 9)
    if inv["kind"] == "GST" and inv["template"] != "D":
        c.drawString(15 * mm, y, "HSN/SAC as per item master. Tax is payable on reverse charge: No")
        y -= 5 * mm
    c.drawString(15 * mm, y, "Bank details for payment:")
    y -= 5 * mm
    c.drawString(15 * mm, y, f"{L['bank']}: {inv['bank_account']}    {L['code']}: {inv['bank_code']}")
    y -= 8 * mm
    c.drawString(15 * mm, y, "Payment terms: 30 days from invoice date.")
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(15 * mm, 30 * mm, "This is a computer generated invoice." if inv["template"] != "D"
                 else "Kindly pay at the earliest. Thank you for your business.")
    c.showPage()
    c.save()


def make_scanned(inv, path):
    """Render the invoice, then turn it into an image-only PDF with slight skew and noise."""
    import pypdfium2 as pdfium
    from PIL import Image, ImageFilter
    buf = io.BytesIO()
    draw_invoice(inv, buf)
    pdf = pdfium.PdfDocument(buf.getvalue())
    img = pdf[0].render(scale=2.2).to_pil().convert("L")
    img = img.rotate(0.6, expand=False, fillcolor=255, resample=Image.BICUBIC)
    rnd = random.Random(7)
    px = img.load()
    w, h = img.size
    for _ in range(int(w * h * 0.002)):
        x, yy = rnd.randrange(w), rnd.randrange(h)
        px[x, yy] = rnd.choice([90, 140, 200])
    img = img.filter(ImageFilter.GaussianBlur(0.5))
    img.convert("RGB").save(path, "PDF", resolution=200)


# ---------------------------------------------------------------- write everything
def write_csv(path, rows, fields):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    INBOX.mkdir(parents=True, exist_ok=True)
    for old in INBOX.glob("*.pdf"):
        old.unlink()
    write_csv(DATA / "vendor_master.csv", VENDORS, list(VENDORS[0].keys()))
    write_csv(DATA / "purchase_orders.csv",
              [dict(po_number=p, vendor_id=v, buyer_entity=e, line_no=n, item_code=ic, description=d, qty=q,
                    unit_price=up, currency=cur, status="open") for p, v, e, n, ic, d, q, up, cur in PO_LINES],
              ["po_number", "vendor_id", "buyer_entity", "line_no", "item_code", "description", "qty", "unit_price",
               "currency", "status"])
    write_csv(DATA / "goods_receipts.csv",
              [dict(grn_number=g, po_number=p, line_no=n, qty_received=q, receipt_date=d) for p, n, q, g, d in GRNS],
              ["grn_number", "po_number", "line_no", "qty_received", "receipt_date"])
    ledger = list(LEDGER)
    # older months for the two monthly service POs, so PO quantities add up
    for po, months in PRIOR_CONSUMPTION_NOTE.items():
        listed = sum(1 for r in LEDGER if r["po_number"] == po)
        vid = "V003" if po.endswith("1106") else "V005"
        for k in range(months - listed):
            ledger.append(dict(vendor_id=vid, invoice_number=f"HIST-{po[-4:]}-{k+1:02d}", invoice_date=f"2026-0{k%8+1}-05",
                               currency="INR", total=45430.00 if vid == "V003" else 47200.00, po_number=po,
                               billed_lines="1:1", service_period=f"FY month {k+1}", status="paid"))
    write_csv(DATA / "ap_ledger.csv", ledger, list(LEDGER[0].keys()))

    truth = []
    for inv in INVOICES:
        path = INBOX / inv["file"]
        if inv["scanned"]:
            make_scanned(inv, path)
        else:
            draw_invoice(inv, str(path))
        truth.append(dict(
            file=inv["file"], edge_case=inv["edge_case"], expected_route=inv["expected_route"],
            expected_reasons=inv["expected_reasons"],
            fields=dict(vendor_id=inv["vendor_id"] or None, invoice_number=inv["invoice_number"],
                        invoice_date=inv["invoice_date"], po_number=inv["po_number"], currency=inv["currency"],
                        net_amount=inv["net"], tax_amount=inv["tax"], total_amount=inv["total"],
                        supplier_tax_id=inv["supplier_tax_id"], bank_account=inv["bank_account"],
                        line_count=len(inv["lines"]))))
    (DATA / "ground_truth.json").write_text(json.dumps(
        {"note": "SYNTHETIC test set. Expected routes were decided by hand from the AP policy, before running the pipeline.",
         "invoices": truth}, indent=2))
    print(f"Wrote {len(INVOICES)} synthetic invoices to {INBOX}")


if __name__ == "__main__":
    main()
