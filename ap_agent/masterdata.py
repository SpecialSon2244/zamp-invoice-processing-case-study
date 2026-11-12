"""Loads the procurement side: vendor master, POs, goods receipts and the AP ledger."""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .config import DATA


def _read(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


@dataclass
class MasterData:
    vendors: dict                      # vendor_id -> row
    po_lines: dict                     # po_number -> list of line dicts
    grn: dict                          # (po, line_no) -> qty received
    ledger: list                       # invoices already booked (list of dicts)
    batch: list = field(default_factory=list)   # invoices accepted earlier in this run

    @classmethod
    def load(cls, folder: Path = DATA) -> "MasterData":
        vendors = {r["vendor_id"]: r for r in _read(folder / "vendor_master.csv")}
        for v in vendors.values():
            v["tds_rate"] = float(v["tds_rate"] or 0)
        po_lines = defaultdict(list)
        for r in _read(folder / "purchase_orders.csv"):
            r["line_no"], r["qty"], r["unit_price"] = int(r["line_no"]), float(r["qty"]), float(r["unit_price"])
            po_lines[r["po_number"]].append(r)
        grn = defaultdict(float)
        for r in _read(folder / "goods_receipts.csv"):
            grn[(r["po_number"], int(r["line_no"]))] += float(r["qty_received"])
        ledger = _read(folder / "ap_ledger.csv")
        for r in ledger:
            r["total"] = float(r["total"])
        return cls(vendors, dict(po_lines), dict(grn), ledger)

    # ---- helpers
    def all_booked(self) -> list[dict]:
        return self.ledger + self.batch

    def billed_qty(self, po: str, line_no: int) -> float:
        total = 0.0
        for r in self.all_booked():
            if r["po_number"] != po:
                continue
            for part in (r.get("billed_lines") or "").split(";"):
                if ":" in part:
                    ln, q = part.split(":")
                    if int(ln) == line_no:
                        total += float(q)
        return total

    def vendor_by_tax_id(self, tax_id: str):
        return next((v for v in self.vendors.values() if v["tax_id"] == tax_id), None)

    def vendor_by_pan(self, pan: str):
        return next((v for v in self.vendors.values() if pan and v["pan"] == pan), None)
