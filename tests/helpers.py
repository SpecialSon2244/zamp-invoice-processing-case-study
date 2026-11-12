"""Build an Extraction by hand so each rule can be tested without a PDF."""
from datetime import date

from ap_agent.extract import Extraction, Field, reconcile
from ap_agent.masterdata import MasterData


def make_ex(**over):
    base = dict(supplier_name="Sri Lakshmi Packaging Pvt Ltd", supplier_tax_id="29AAFCS7731K1ZU",
                buyer_tax_id="29AABCK4821M1Z9", tax_regime="GST", invoice_number="SLP/26-27/0999",
                invoice_date=date(2026, 11, 4), po_number="KAV-PO-2026-1101", service_period=None, currency="INR",
                net_amount=25750.0, tax_amount=4635.0, total_amount=30385.0, bank_account="50200041187723",
                bank_code="HDFC0001234", reverse_charge_note=False)
    lines = over.pop("lines", [
        {"item_code": "PK-5PLY-450", "description": "Corrugated box 5-ply 450x350x300", "qty": 500, "unit": "Nos",
         "unit_price": 42.0, "amount": 21000.0},
        {"item_code": "PK-FOAM-IN", "description": "EPE foam insert set", "qty": 500, "unit": "Set",
         "unit_price": 9.5, "amount": 4750.0}])
    taxes = over.pop("taxes", [{"type": "CGST", "rate": 9.0, "amount": 2317.5},
                               {"type": "SGST", "rate": 9.0, "amount": 2317.5}])
    conf = over.pop("conf", {})
    base.update(over)
    ex = Extraction()
    for k, v in base.items():
        ex.fields[k] = Field(v, conf.get(k, 0.95) if v is not None else 0.0, "test")
    ex.lines, ex.taxes = lines, taxes
    return ex


def md():
    return MasterData.load()


def codes(findings):
    return {f.code for f in findings}
