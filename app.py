"""Review UI:   streamlit run app.py

Three screens:
  Live run      pick or upload invoices and watch each stage execute
  Review queue  the human-in-the-loop step: see why, look at the PDF, approve or reject, leave a note
  Dashboard     history across runs, route counts, and the full audit trail per invoice
"""
import json
import os
from datetime import date
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="AP invoice agent", page_icon="🧾", layout="wide")

import pandas as pd

from ap_agent.config import DATA, Policy
from ap_agent.store import Store

ROUTE_STYLE = {"AUTO_APPROVE": ("✅ Auto-approve", "green"), "NEEDS_REVIEW": ("🟠 Needs review", "orange"),
               "REJECT": ("⛔ Reject, return to vendor", "red")}
STATUS_ICON = {"ok": "✅", "warn": "🟠", "fail": "⛔"}
FINAL_STATUS = {
    "AUTO_APPROVE": "Auto-approved",
    "NEEDS_REVIEW": "Waiting for review",
    "REJECT": "Returned to vendor",
    "HUMAN_APPROVED": "Approved by reviewer",
    "HUMAN_RETURNED": "Returned to vendor by reviewer",
    "HUMAN_REJECTED": "Rejected by reviewer",
}
DECISION_LABEL = {"APPROVED": "Approved", "RETURNED": "Returned to vendor", "REJECTED": "Rejected"}
UPLOADS = DATA / "uploads"


@st.cache_resource
def get_store(db_path: str | None):
    return Store(Path(db_path)) if db_path else Store()


store = get_store(os.environ.get("AP_AGENT_DB"))
st.sidebar.title("🧾 AP invoice agent")
st.sidebar.caption("Case study build. All invoices, vendors and POs are synthetic test data.")
page = st.sidebar.radio("Screen", ["Live run", "Review queue", "Dashboard"])
as_of = st.sidebar.date_input("Business date", date(2026, 11, 12))
use_llm = st.sidebar.toggle("LLM fallback for weak fields", value=False,
                            help="Needs LLM_API_KEY. Off by default; the rules run without it.")
policy = Policy(as_of=as_of)


def invoice_key(run_id, file):
    return f"{file}  ({run_id})"


def render_pdf(path, width=520):
    try:
        import pypdfium2 as pdfium
        st.image(pdfium.PdfDocument(path)[0].render(scale=1.3).to_pil(), width=width)
    except Exception as e:  # file moved or unreadable
        st.caption(f"Preview not available ({e})")


def fields_table(res):
    rows = [{"field": k, "value": v["value"], "confidence": v["confidence"], "method": v["method"]}
            for k, v in res["fields"].items() if k not in ("tax_regime", "reverse_charge_note")]
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, use_container_width=True,
                 column_config={"confidence": st.column_config.ProgressColumn("confidence", min_value=0, max_value=1,
                                                                             format="%.2f")})


def decision_card(res):
    d = res["decision"]
    label, color = ROUTE_STYLE[d["route"]]
    cur = res["fields"]["currency"]["value"] or ""
    total = res["fields"]["total_amount"]["value"]
    st.markdown(f"### :{color}[{label}]")
    extra = (f" | **Payable after TDS:** {cur} {d['payable_amount']:,.2f}" if res["tds"] else "")
    st.markdown(f"**Vendor:** {res['vendor_name'] or '?'} | **Invoice:** "
                f"{res['fields']['invoice_number']['value'] or '(none)'} | **Total:** "
                + (f"{cur} {total:,.2f}" if total is not None else "?")
                + f" | **Lowest critical-field confidence:** {d['min_critical_confidence']:.2f}" + extra)
    if d["reasons"]:
        st.markdown(f"**Owner:** {d['owner']}")
        for r in d["reasons"]:
            st.markdown(f"- **{r['code']}**: {r['message']}" + (f"  \n  *Next step:* {r['action']}" if r["action"] else ""))
    if d.get("also_noted"):
        with st.expander("Also found (would need review if the vendor fixes the above)"):
            for r in d["also_noted"]:
                st.markdown(f"- **{r['code']}**: {r['message']}")


def count_bar_chart(series, category_title):
    """Readable bar chart with a fixed height and an integer count axis."""
    import altair as alt

    data = series.rename_axis("label").reset_index(name="count")
    height = max(220, 36 * len(data) + 40)
    chart = (
        alt.Chart(data)
        .mark_bar(color="#1f6feb", size=22)
        .encode(
            y=alt.Y("label:N", sort="-x", title=category_title),
            x=alt.X("count:Q", title="Invoices",
                    axis=alt.Axis(tickMinStep=1, format="d"),
                    scale=alt.Scale(domainMin=0, nice=True)),
            tooltip=[
                alt.Tooltip("label:N", title=category_title),
                alt.Tooltip("count:Q", title="Invoices", format="d"),
            ],
        )
        .properties(height=height)
    )
    st.altair_chart(chart, use_container_width=True)


# ------------------------------------------------------------------ Live run
if page == "Live run":
    import time

    from ap_agent.masterdata import MasterData
    from ap_agent.pipeline import new_run_id, process_invoice

    st.header("Live run")
    st.write("Pick invoices from the inbox or upload your own PDF. Each stage shows up as it finishes.")
    inbox = sorted((DATA / "inbox").glob("*.pdf"))
    if not inbox:
        st.warning("No invoices in data/inbox. Add PDFs there, or upload them below.")
    picked = st.multiselect("Invoices from data/inbox", [p.name for p in inbox],
                            default=[inbox[0].name] if inbox else [])
    up = st.file_uploader("...or upload invoice PDFs", type="pdf", accept_multiple_files=True)
    slow = st.checkbox("Demo pace (adds a short pause between stages so they are easy to follow)", value=True)
    if st.button("▶ Run", type="primary"):
        files = [DATA / "inbox" / n for n in picked]
        for u in up or []:
            UPLOADS.mkdir(parents=True, exist_ok=True)
            p = UPLOADS / u.name
            p.write_bytes(u.getvalue())
            files.append(p)
        md = MasterData.load()
        run_id = new_run_id()
        store.start_run(run_id, "ui", use_llm)
        counts = {}
        for f in files:
            st.subheader(f.name)
            left, right = st.columns([3, 2])
            with right:
                render_pdf(str(f), 420)
            with left:
                box = st.status(f"Processing {f.name}", expanded=True)

                def on_stage(stage, box=box):
                    box.write(f"{STATUS_ICON[stage['status']]} **{stage['title']}** ({stage['ms']} ms): {stage['summary']}")
                    if slow:
                        time.sleep(0.35)

                res = process_invoice(f, md, policy, store, run_id, use_llm, on_stage)
                store.save_invoice(run_id, res)
                route = res["decision"]["route"]
                counts[route] = counts.get(route, 0) + 1
                box.update(label=f"{f.name}: {ROUTE_STYLE[route][0]}", state="complete" if route == "AUTO_APPROVE"
                           else "error", expanded=True)
                decision_card(res)
                with st.expander("Extracted fields and confidence"):
                    fields_table(res)
                    if res["lines"]:
                        st.dataframe(pd.DataFrame(res["lines"]).drop(columns=["evidence"], errors="ignore"),
                                     hide_index=True)
                with st.expander("PO / goods receipt match"):
                    st.dataframe(pd.DataFrame(res["match"]["lines"]), hide_index=True)
                with st.expander("Every finding, stage by stage"):
                    for s in res["stages"]:
                        for x in s["findings"]:
                            st.markdown(f"{s['title']}: `{x['severity']}` **{x['code']}** {x['message']}")
            st.divider()
        store.finish_run(run_id, counts)
        st.success(f"Run {run_id} saved. " + ", ".join(f"{ROUTE_STYLE[k][0]}: {v}" for k, v in counts.items()))

# ------------------------------------------------------------------ Review queue
elif page == "Review queue":
    st.header("Review queue")
    flash = st.session_state.pop("review_result", None)
    if flash:
        st.success(f"{DECISION_LABEL[flash['decision']]} by {flash['reviewer']}. Logged with the note: {flash['comment']}")
        st.caption(f"Audit trail for {flash['file']}")
        st.dataframe(pd.DataFrame(store.audit_for(flash["run_id"], flash["file"])),
                     hide_index=True, use_container_width=True)
        st.divider()

    q = store.review_queue()
    if not q:
        st.info("Nothing waiting for review. Run some invoices first (Live run, or `python run.py`).")
    else:
        df = pd.DataFrame([{"run": r["run_id"], "file": r["file"], "vendor": r["vendor"], "invoice": r["invoice_number"],
                            "total": f"{r['currency']} {r['total']:,.2f}" if r["total"] else "", "owner": r["owner"],
                            "why": ", ".join(x["code"] for x in json.loads(r["reasons"]))} for r in q])
        st.dataframe(df, hide_index=True, use_container_width=True)
        options = [invoice_key(r["run_id"], r["file"]) for r in q]
        # Drop a stale selection (invoice already decided, or from an older run) before the widget runs.
        if st.session_state.get("review_queue_id") not in options:
            st.session_state.pop("review_queue_id", None)
        choice = st.selectbox("Open an invoice", options, key="review_queue_id")
        item = next(r for r in q if invoice_key(r["run_id"], r["file"]) == choice)
        res = json.loads(item["result"])
        left, right = st.columns([3, 2])
        with left:
            decision_card(res)
            fields_table(res)
            reviewer = st.text_input("Your name", value="AP reviewer", key=f"reviewer_{choice}")
            comment = st.text_area("Note for the audit trail (required)",
                                   placeholder="e.g. Called vendor on master number, bank change confirmed by email from finance head",
                                   key=f"review_note_{choice}")
            b1, b2, b3 = st.columns(3)
            for col, label, decision in [(b1, "✅ Approve", "APPROVED"), (b2, "↩ Return to vendor", "RETURNED"),
                                         (b3, "⛔ Reject", "REJECTED")]:
                if col.button(label, use_container_width=True, key=f"review_{decision}_{choice}"):
                    if not (comment or "").strip():
                        st.error("Add a note first. Every human decision needs a reason on record.")
                    else:
                        store.human_decision(item["run_id"], item["file"], decision, reviewer, comment.strip())
                        st.session_state["review_result"] = {
                            "run_id": item["run_id"], "file": item["file"], "decision": decision,
                            "reviewer": reviewer, "comment": comment.strip(),
                        }
                        st.session_state.pop("review_queue_id", None)
                        st.session_state.pop(f"review_note_{choice}", None)
                        st.rerun()
            with st.expander("Audit trail for this invoice", expanded=False):
                st.dataframe(pd.DataFrame(store.audit_for(item["run_id"], item["file"])), hide_index=True)
        with right:
            render_pdf(res.get("path", ""), 480)

# ------------------------------------------------------------------ Dashboard
else:
    st.header("Dashboard")
    runs, inv = store.runs(), store.invoices()
    if not inv:
        st.info("No runs yet.")
    else:
        df = pd.DataFrame(inv)
        df["final_decision"] = df["status"].map(lambda s: FINAL_STATUS.get(s, s))
        c = st.columns(5)
        c[0].metric("Runs", len(runs))
        c[1].metric("Invoices processed", len(df))
        c[2].metric("Auto-approved", int((df.route == "AUTO_APPROVE").sum()))
        c[3].metric("Waiting for a person", int((df.status == "NEEDS_REVIEW").sum()))
        c[4].metric("Returned / rejected", int(df.status.isin(["REJECT", "HUMAN_RETURNED", "HUMAN_REJECTED"]).sum()))
        st.subheader("Runs")
        st.dataframe(pd.DataFrame(runs), hide_index=True, use_container_width=True)
        l, r = st.columns(2)
        with l:
            st.subheader("Routes")
            count_bar_chart(df.route.map({
                "AUTO_APPROVE": "Auto-approve",
                "NEEDS_REVIEW": "Needs review",
                "REJECT": "Reject, return to vendor",
            }).value_counts(), "Route")
        with r:
            st.subheader("Why invoices stop")
            reasons = pd.Series([x["code"] for s in df.reasons for x in json.loads(s)])
            if len(reasons):
                count_bar_chart(reasons.value_counts(), "Reason")
        st.subheader("All invoices")
        run_pick = st.selectbox("Run", ["all"] + [x["run_id"] for x in runs], key="dashboard_run")
        view = df if run_pick == "all" else df[df.run_id == run_pick]
        st.dataframe(view[["run_id", "file", "vendor", "invoice_number", "currency", "total", "route",
                           "final_decision", "owner"]], hide_index=True, use_container_width=True)
        st.subheader("Audit trail")
        opts = [invoice_key(row.run_id, row.file) for row in view[["run_id", "file"]].itertuples(index=False)]
        if opts:
            if st.session_state.get("dashboard_invoice_id") not in opts:
                st.session_state.pop("dashboard_invoice_id", None)
            pick = st.selectbox("Invoice", opts, key="dashboard_invoice_id")
            file, run_id = pick.rsplit("  (", 1)
            run_id = run_id[:-1]
            st.dataframe(pd.DataFrame(store.audit_for(run_id, file)), hide_index=True, use_container_width=True)
