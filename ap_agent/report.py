"""Writes the batch outputs: Excel workbook, CSV, per-invoice JSON and a markdown run report."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pandas as pd

from .rules import money

ROUTE_LABEL = {"AUTO_APPROVE": "Auto-approve", "NEEDS_REVIEW": "Needs review", "REJECT": "Reject (return to vendor)"}


def _v(res, f):
    return res["fields"].get(f, {}).get("value")


def summary_rows(results):
    rows = []
    for r in results:
        d = r["decision"]
        rows.append({
            "file": r["file"], "vendor_id": r["vendor_id"], "vendor": r["vendor_name"],
            "invoice_number": _v(r, "invoice_number"), "invoice_date": _v(r, "invoice_date"),
            "po_number": r["match"].get("po_number") or _v(r, "po_number"),
            "po_inferred": r["match"].get("po_inferred", False), "currency": _v(r, "currency"),
            "net": _v(r, "net_amount"), "tax": _v(r, "tax_amount"), "total": _v(r, "total_amount"),
            "tds": r["tds"].get("tds_amount"), "payable": d["payable_amount"], "source": r["source"],
            "min_confidence": d["min_critical_confidence"], "route": d["route"], "owner": d["owner"],
            "reason_codes": ", ".join(x["code"] for x in d["reasons"]),
            "reasons": " | ".join(x["message"] for x in d["reasons"]),
            "next_action": " | ".join(x["action"] for x in d["reasons"] if x["action"]),
        })
    return rows


def write_outputs(run_id: str, results: list, out_dir: Path, as_of, llm: bool) -> Path:
    out = out_dir / run_id
    (out / "decisions").mkdir(parents=True, exist_ok=True)
    rows = summary_rows(results)
    df = pd.DataFrame(rows)
    df.to_csv(out / "summary.csv", index=False)
    findings = [{"file": r["file"], "stage": st["title"], **f} for r in results for st in r["stages"]
                for f in st["findings"]]
    fields = [{"file": r["file"], "field": k, **v} for r in results for k, v in r["fields"].items()]
    with pd.ExcelWriter(out / "summary.xlsx", engine="openpyxl") as xw:
        df.to_excel(xw, sheet_name="Decisions", index=False)
        df[df.route == "NEEDS_REVIEW"][["file", "vendor", "invoice_number", "total", "owner", "reasons",
                                        "next_action"]].to_excel(xw, sheet_name="Review queue", index=False)
        df[df.route == "REJECT"][["file", "vendor", "invoice_number", "total", "reasons", "next_action"]] \
            .to_excel(xw, sheet_name="Return to vendor", index=False)
        pd.DataFrame(findings).to_excel(xw, sheet_name="All findings", index=False)
        pd.DataFrame(fields).to_excel(xw, sheet_name="Field confidence", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(
                    60, max(10, max(len(str(c.value or "")) for c in col) + 2))
            ws.freeze_panes = "A2"
    for r in results:
        (out / "decisions" / (Path(r["file"]).stem + ".json")).write_text(json.dumps(r, indent=2, default=str))

    c = Counter(r["decision"]["route"] for r in results)
    lines = [f"# AP invoice run {run_id}", "",
             f"As-of date: {as_of}. LLM step: {'on' if llm else 'off'}. Invoices: {len(results)}. "
             "Inputs are synthetic test data.", "",
             "| Route | Count |", "|---|---|"]
    lines += [f"| {ROUTE_LABEL[k]} | {c.get(k, 0)} |" for k in ROUTE_LABEL]
    lines += ["", "## Decisions", "", "| File | Vendor | Invoice | Total | Route | Why |", "|---|---|---|---|---|---|"]
    for row in rows:
        tot = money(row["currency"], row["total"]) if row["total"] is not None else "?"
        why = row["reason_codes"] or "; ".join(
            (["read by OCR, amounts reconciled"] if row["source"] == "ocr" else [])
            + (["PO inferred"] if row["po_inferred"] else []) + ["all checks passed"])
        lines.append(f"| {row['file']} | {row['vendor']} | {row['invoice_number'] or '(none)'} | {tot} | "
                     f"{ROUTE_LABEL[row['route']]} | {why} |")
    lines += ["", "## What a person needs to do", ""]
    for r in results:
        d = r["decision"]
        if d["route"] == "AUTO_APPROVE":
            continue
        lines.append(f"**{r['file']}** ({ROUTE_LABEL[d['route']]}, owner: {d['owner']})")
        for x in d["reasons"]:
            lines.append(f"- {x['message']}" + (f". Next step: {x['action']}" if x["action"] else ""))
        lines.append("")
    (out / "run_report.md").write_text("\n".join(lines))
    latest = out_dir / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(out.name)
    return out
