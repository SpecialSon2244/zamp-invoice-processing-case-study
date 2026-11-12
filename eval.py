"""Measure the pipeline against the hand-written ground truth.

  python eval.py            # clean PDFs as generated
  python eval.py --scanned  # also re-run every invoice as a degraded scan (OCR stress test)

Reports per-field extraction accuracy, routing precision / recall per route, a confusion
matrix, reason-code recall, and the one number AP cares about most: invoices that were
auto-approved when they should not have been. Writes outputs/eval_report.md.
"""
import argparse
import json
import random
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

from ap_agent.config import DATA, OUTPUTS, Policy
from ap_agent.pipeline import ROUTES, run_batch

FIELDS = ["vendor_id", "invoice_number", "invoice_date", "po_number", "currency", "net_amount", "tax_amount",
          "total_amount", "supplier_tax_id", "bank_account", "line_count"]


def predicted(res, f):
    if f == "vendor_id":
        return res["vendor_id"]
    if f == "line_count":
        return len(res["lines"])
    return res["fields"].get(f, {}).get("value")


def same(a, b):
    if isinstance(b, (int, float)) and not isinstance(b, bool) and a is not None:
        try:
            return abs(float(a) - float(b)) < 0.01
        except (TypeError, ValueError):
            return False
    return a == b


def make_scans(src: Path, dst: Path, seed=11):
    """Degrade every PDF: lower resolution, skew, speckle noise, blur. Image only, no text layer."""
    import pypdfium2 as pdfium
    from PIL import Image, ImageFilter
    rnd = random.Random(seed)
    for p in sorted(src.glob("*.pdf")):
        img = pdfium.PdfDocument(str(p))[0].render(scale=1.6).to_pil().convert("L")
        img = img.rotate(rnd.uniform(-1.2, 1.2), fillcolor=255, resample=Image.BICUBIC)
        px, (w, h) = img.load(), img.size
        for _ in range(int(w * h * 0.004)):
            px[rnd.randrange(w), rnd.randrange(h)] = rnd.choice([60, 120, 180])
        img.filter(ImageFilter.GaussianBlur(0.7)).convert("RGB").save(dst / p.name, "PDF", resolution=150)


def evaluate(results, truth, label):
    by_file = {t["file"]: t for t in truth}
    field_hits, field_n = Counter(), Counter()
    errors = []
    conf = {a: Counter() for a in ROUTES}
    reason_hit = reason_n = 0
    for r in results:
        t = by_file[r["file"]]
        for f in FIELDS:
            exp = t["fields"][f]
            field_n[f] += 1
            if same(predicted(r, f), exp):
                field_hits[f] += 1
            else:
                errors.append(f"{r['file']}: {f} expected {exp!r}, got {predicted(r, f)!r}")
        conf[t["expected_route"]][r["decision"]["route"]] += 1
        codes = {x["code"] for st in r["stages"] for x in st["findings"]}
        if r["source"] == "ocr":
            codes.add("OCR")
        for c in t["expected_reasons"]:
            reason_n += 1
            reason_hit += c in codes
    rows = []
    for route in ROUTES:
        tp = conf[route][route]
        pred = sum(conf[a][route] for a in ROUTES)
        act = sum(conf[route].values())
        rows.append((route, tp, pred, act, tp / pred if pred else float("nan"), tp / act if act else float("nan")))
    false_auto = sum(conf[a]["AUTO_APPROVE"] for a in ROUTES if a != "AUTO_APPROVE")
    total_fields = sum(field_n.values())
    out = [f"## {label}", "",
           f"Invoices: {len(results)}. Routing accuracy: {sum(conf[a][a] for a in ROUTES)}/{len(results)}. "
           f"Field accuracy overall: {sum(field_hits.values())}/{total_fields} "
           f"({sum(field_hits.values()) / total_fields:.1%}).", "",
           f"**Invoices auto-approved that should not have been: {false_auto}**", "",
           "| Field | Correct | Accuracy |", "|---|---|---|"]
    out += [f"| {f} | {field_hits[f]}/{field_n[f]} | {field_hits[f] / field_n[f]:.0%} |" for f in FIELDS]
    out += ["", "| Route | Precision | Recall | Predicted | Actual |", "|---|---|---|---|---|"]
    out += [f"| {r} | {p:.0%} | {rc:.0%} | {pr} | {ac} |" for r, tp, pr, ac, p, rc in rows]
    out += ["", "Confusion matrix (rows = expected, columns = predicted):", "",
            "| expected \\ predicted | " + " | ".join(ROUTES) + " |", "|---" * (len(ROUTES) + 1) + "|"]
    out += [f"| {a} | " + " | ".join(str(conf[a][b]) for b in ROUTES) + " |" for a in ROUTES]
    out += ["", f"Expected reason codes found: {reason_hit}/{reason_n}", ""]
    if errors:
        out += ["Field errors:", ""] + [f"- {e}" for e in errors] + [""]
    mis = [f"- {r['file']}: expected {by_file[r['file']]['expected_route']}, got {r['decision']['route']} "
           f"({', '.join(x['code'] for x in r['decision']['reasons']) or 'no reasons'})"
           for r in results if r["decision"]["route"] != by_file[r["file"]]["expected_route"]]
    if mis:
        out += ["Routing differences:", ""] + mis + [""]
    return out, {"field_accuracy": sum(field_hits.values()) / total_fields, "false_auto_approvals": false_auto,
                 "routing_correct": sum(conf[a][a] for a in ROUTES), "n": len(results)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scanned", action="store_true", help="also run the OCR stress test")
    ap.add_argument("--as-of", default="2026-11-12")
    ap.add_argument("--seeds", default="11,29", help="noise seeds for the scan test. 11 was used while fixing "
                                                    "the parser; 29 was held out and only run after the fixes")
    a = ap.parse_args()
    truth = json.loads((DATA / "ground_truth.json").read_text())["invoices"]
    policy = Policy(as_of=date.fromisoformat(a.as_of))
    report = ["# Evaluation report", "",
              "All inputs are SYNTHETIC. I wrote the invoices, the ground truth and the rules, so the clean-PDF "
              "numbers mainly show the rules do what I designed them to do. They are not evidence of accuracy on "
              "real vendor invoices. The scanned stress test is a harder, more honest check of the extraction layer.",
              ""]
    _, res = run_batch(sorted((DATA / "inbox").glob("*.pdf")), policy)
    sec, summary = evaluate(res, truth, "Clean PDFs (as generated)")
    report += sec
    print(f"clean:   routing {summary['routing_correct']}/{summary['n']}, fields {summary['field_accuracy']:.1%}, "
          f"false auto-approvals {summary['false_auto_approvals']}")
    if a.scanned:
        for seed in [int(x) for x in a.seeds.split(",")]:
            with tempfile.TemporaryDirectory() as tmp:
                make_scans(DATA / "inbox", Path(tmp), seed)
                _, res2 = run_batch(sorted(Path(tmp).glob("*.pdf")), policy)
            role = "used while fixing the parser" if seed == 11 else "held out, run after the fixes"
            sec, s2 = evaluate(res2, truth, f"Stress test, seed {seed} ({role}): every invoice as a degraded scan")
            report += sec
            print(f"scanned seed {seed}: routing {s2['routing_correct']}/{s2['n']}, fields {s2['field_accuracy']:.1%}, "
                  f"false auto-approvals {s2['false_auto_approvals']}")
    OUTPUTS.mkdir(exist_ok=True)
    (OUTPUTS / "eval_report.md").write_text("\n".join(report))
    print(f"Wrote {OUTPUTS / 'eval_report.md'}")


if __name__ == "__main__":
    main()
