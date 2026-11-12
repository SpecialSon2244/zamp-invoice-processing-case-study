"""Run history, decisions, human review actions and the audit log, in one SQLite file."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .config import OUTPUTS

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, source TEXT,
    invoices INTEGER, auto_approve INTEGER, needs_review INTEGER, reject INTEGER, llm INTEGER);
CREATE TABLE IF NOT EXISTS invoices (run_id TEXT, file TEXT, vendor TEXT, invoice_number TEXT, invoice_date TEXT,
    currency TEXT, total REAL, route TEXT, status TEXT, owner TEXT, reasons TEXT, result TEXT,
    PRIMARY KEY (run_id, file));
CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, run_id TEXT, file TEXT,
    stage TEXT, actor TEXT, event TEXT, detail TEXT);
"""


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path = OUTPUTS / "ap_agent.db"):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.jsonl = path.parent / "audit_log.jsonl"

    def audit(self, run_id, file, stage, event, detail=None, actor="agent"):
        rec = {"ts": now(), "run_id": run_id, "file": file, "stage": stage, "actor": actor, "event": event,
               "detail": detail or {}}
        self.db.execute("INSERT INTO audit (ts, run_id, file, stage, actor, event, detail) VALUES (?,?,?,?,?,?,?)",
                        (rec["ts"], run_id, file, stage, actor, event, json.dumps(detail or {}, default=str)))
        self.db.commit()
        with open(self.jsonl, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")

    def start_run(self, run_id, source, llm):
        self.db.execute("INSERT INTO runs (run_id, started_at, source, invoices, auto_approve, needs_review, reject, llm)"
                        " VALUES (?,?,?,0,0,0,0,?)", (run_id, now(), source, int(llm)))
        self.db.commit()

    def save_invoice(self, run_id, res: dict):
        d = res["decision"]
        self.db.execute("INSERT OR REPLACE INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            run_id, res["file"], res["vendor_name"], res["fields"]["invoice_number"]["value"],
            res["fields"]["invoice_date"]["value"], res["fields"]["currency"]["value"],
            res["fields"]["total_amount"]["value"], d["route"], d["route"], d["owner"],
            json.dumps(d["reasons"]), json.dumps(res, default=str)))
        self.db.commit()

    def finish_run(self, run_id, counts: dict):
        self.db.execute("UPDATE runs SET finished_at=?, invoices=?, auto_approve=?, needs_review=?, reject=? "
                        "WHERE run_id=?", (now(), sum(counts.values()), counts.get("AUTO_APPROVE", 0),
                                           counts.get("NEEDS_REVIEW", 0), counts.get("REJECT", 0), run_id))
        self.db.commit()

    def human_decision(self, run_id, file, decision, reviewer, comment):
        self.db.execute("UPDATE invoices SET status=? WHERE run_id=? AND file=?",
                        (f"HUMAN_{decision}", run_id, file))
        self.db.commit()
        self.audit(run_id, file, "review", f"human {decision.lower()}", {"comment": comment}, actor=reviewer)

    # ---- reads for the dashboard
    def runs(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM runs ORDER BY started_at DESC")]

    def invoices(self, run_id=None):
        q, a = "SELECT * FROM invoices", ()
        if run_id:
            q, a = q + " WHERE run_id=?", (run_id,)
        return [dict(r) for r in self.db.execute(q + " ORDER BY run_id DESC, file", a)]

    def review_queue(self):
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM invoices WHERE status='NEEDS_REVIEW' ORDER BY run_id DESC, file")]

    def audit_for(self, run_id, file):
        return [dict(r) for r in self.db.execute(
            "SELECT ts, stage, actor, event, detail FROM audit WHERE run_id=? AND file=? ORDER BY id", (run_id, file))]
