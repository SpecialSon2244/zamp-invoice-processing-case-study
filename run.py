"""One command, end to end:   python run.py

Reads every PDF in data/inbox, runs each through the 9 stages, prints each stage live,
and writes outputs/<run_id>/ (summary.xlsx, summary.csv, run_report.md, decisions/*.json)
plus the audit log (outputs/audit_log.jsonl and outputs/ap_agent.db).
"""
import argparse
import sys
from datetime import date
from pathlib import Path

from ap_agent.config import DATA, OUTPUTS, Policy
from ap_agent.pipeline import run_batch
from ap_agent.report import write_outputs
from ap_agent.store import Store

ICON = {"ok": "OK  ", "warn": "WARN", "fail": "FAIL"}
ROUTE = {"AUTO_APPROVE": "AUTO-APPROVE", "NEEDS_REVIEW": "NEEDS REVIEW", "REJECT": "REJECT"}


def main():
    ap = argparse.ArgumentParser(description="AP invoice agent: PDF in, reasoned decision out")
    ap.add_argument("paths", nargs="*", help="invoice PDFs or folders (default: data/inbox)")
    ap.add_argument("--as-of", default="2026-11-12", help="business date used for date checks (YYYY-MM-DD)")
    ap.add_argument("--llm", action="store_true", help="use the optional LLM fallback for weak fields")
    ap.add_argument("--quiet", action="store_true", help="only print the decision per invoice")
    a = ap.parse_args()

    targets = [Path(p) for p in a.paths] or [DATA / "inbox"]
    files = []
    for t in targets:
        files += sorted(t.glob("*.pdf")) if t.is_dir() else [t]
    if not files:
        sys.exit("No PDFs found")
    policy = Policy(as_of=date.fromisoformat(a.as_of))
    store = Store()

    def on_stage(path, st):
        if st["stage"] == "ingest":
            print(f"\n=== {path.name}")
        if not a.quiet or st["stage"] == "decision":
            print(f"  [{ICON[st['status']]}] {st['title']:<40} {st['summary']}")

    def on_invoice(res):
        d = res["decision"]
        print(f"  -> {ROUTE[d['route']]}" + (f"  owner: {d['owner']}" if d["route"] != "AUTO_APPROVE" else ""))
        for r in d["reasons"]:
            print(f"     - {r['code']}: {r['message']}")

    run_id, results = run_batch(files, policy, store, a.llm, "cli", on_stage, on_invoice)
    out = write_outputs(run_id, results, OUTPUTS, policy.as_of, a.llm)
    counts = {k: sum(1 for r in results if r["decision"]["route"] == k) for k in ROUTE}
    print("\n" + "-" * 70)
    print(f"Run {run_id}: {len(results)} invoices | " + " | ".join(f"{ROUTE[k]}: {v}" for k, v in counts.items()))
    print(f"Outputs: {out}  (summary.xlsx, summary.csv, run_report.md, decisions/)")
    print(f"Audit log: {OUTPUTS / 'audit_log.jsonl'} and {OUTPUTS / 'ap_agent.db'}")


if __name__ == "__main__":
    main()
