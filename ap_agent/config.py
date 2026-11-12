"""All business thresholds in one place, so an AP lead can read and change them."""
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"

# Buyer entities (the company that receives the invoices). Fictional.
BUYERS = {
    "IN": {"name": "Kaveri Appliances Pvt Ltd", "tax_id": "29AABCK4821M1Z9", "country": "IN"},
    "DE": {"name": "Kaveri Appliances GmbH", "tax_id": "DE318273645", "country": "DE"},
}


@dataclass
class Policy:
    as_of: date = field(default_factory=date.today)
    price_tolerance_pct: float = 2.0          # invoice unit price may exceed PO price by this much
    amount_tolerance_abs: float = 1.0         # rounding slack on totals (in invoice currency)
    approval_limit: dict = field(default_factory=lambda: {"INR": 500000.0, "EUR": 10000.0})
    max_invoice_age_days: int = 180
    min_field_confidence: float = 0.85        # below this a critical field goes to a human
    dup_amount_pct: float = 0.5               # near-duplicate: totals within 0.5%
    dup_window_days: int = 20                 # near-duplicate: dates within 20 days
    dup_number_similarity: float = 0.75
    gst_slabs: tuple = (0.0, 3.0, 5.0, 18.0, 40.0)   # GST rates after the Sept 2025 rationalisation
    eu_vat_rates: dict = field(default_factory=lambda: {"DE": (19.0, 7.0), "NL": (21.0, 9.0)})


CRITICAL_FIELDS = ["invoice_number", "invoice_date", "net_amount", "tax_amount", "total_amount", "supplier_tax_id"]
