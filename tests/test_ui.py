"""UI tests: screens render, and a review decision updates the dashboard status."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ap_agent.store import Store

APP = str(Path(__file__).resolve().parent.parent / "app.py")
FILE_05 = "05_sri_lakshmi_split_po_overbilled.pdf"
FILE_10 = "10_coastal_bank_details_changed.pdf"


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("AP_AGENT_DB", str(tmp_path / "test.db"))


def test_all_screens_render():
    for screen in ["Live run", "Review queue", "Dashboard"]:
        at = AppTest.from_file(APP, default_timeout=60)
        at.run()
        at.sidebar.radio[0].set_value(screen).run()
        assert not at.exception, f"{screen}: {at.exception}"


def test_live_run_processes_an_invoice():
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.checkbox[0].uncheck().run()
    at.button[0].click().run()
    assert not at.exception
    assert any("Auto-approve" in m.value for m in at.markdown)


def test_human_approval_updates_status_and_leaves_queue(tmp_path):
    store = Store(tmp_path / "approval.db")
    res = {
        "file": FILE_10,
        "vendor_name": "Coastal Polymers",
        "fields": {
            "invoice_number": {"value": "CP/26-27/0041"},
            "invoice_date": {"value": "2026-10-20"},
            "currency": {"value": "INR"},
            "total_amount": {"value": 1000.0},
        },
        "decision": {"route": "NEEDS_REVIEW", "owner": "treasury",
                     "reasons": [{"code": "BANK_DETAILS_CHANGED"}]},
    }
    store.start_run("run1", "test", False)
    store.save_invoice("run1", res)
    assert len(store.review_queue()) == 1
    store.human_decision("run1", FILE_10, "APPROVED", "AP reviewer",
                         "Called vendor on the master number.")
    inv = store.invoices()[0]
    assert inv["status"] == "HUMAN_APPROVED"
    assert inv["route"] == "NEEDS_REVIEW"
    assert store.review_queue() == []
    events = [a["event"] for a in store.audit_for("run1", FILE_10)]
    assert any("approved" in e.lower() for e in events)


def test_review_selection_and_approval_updates_dashboard():
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    at.multiselect[0].set_value([FILE_05, FILE_10]).run()
    at.checkbox[0].uncheck().run()
    at.button[0].click().run()
    assert not at.exception

    at.sidebar.radio[0].set_value("Review queue").run()
    assert not at.exception
    box = at.selectbox[0]
    ten = next(o for o in box.options if o.startswith(FILE_10))
    five = next(o for o in box.options if o.startswith(FILE_05))
    assert ten != five
    box.set_value(ten).run()
    assert not at.exception
    assert at.selectbox[0].value == ten

    at.text_area[0].set_value(
        "Called vendor on the number in the master. Bank change confirmed by email from the finance head."
    ).run()
    approve = next(b for b in at.button if "Approve" in b.label)
    approve.click().run()
    assert not at.exception
    assert any("Approved" in s.value for s in at.success)
    assert any(FILE_10 in c.value for c in at.caption)
    # Invoice 10 has left the pending queue; 05 is still waiting.
    remaining = at.selectbox[0].options if at.selectbox else []
    assert all(not o.startswith(FILE_10) for o in remaining)
    assert any(o.startswith(FILE_05) for o in remaining)

    at.sidebar.radio[0].set_value("Dashboard").run()
    assert not at.exception
    waiting = next(m for m in at.metric if m.label == "Waiting for a person")
    assert int(waiting.value) == 1
    found = False
    for table in at.dataframe:
        val = table.value
        if val is None or "final_decision" not in getattr(val, "columns", []):
            continue
        rows = val[val["file"].astype(str).str.startswith("10_coastal")]
        if len(rows):
            found = True
            assert rows["final_decision"].iloc[0] == "Approved by reviewer"
    assert found, "Dashboard invoice table did not show the final decision"
