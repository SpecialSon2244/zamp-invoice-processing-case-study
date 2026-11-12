# AP invoice agent: PDF in, reasoned decision out

**Abhiram Ramakrishnan, Zamp AI Solutions Analyst case study, PS-1 (invoice processing).** All data synthetic.

**What it does.** Takes a vendor invoice PDF, text or scanned, and runs it through nine visible stages: read (text layer or OCR), extract fields with a confidence score, identify the vendor and check bank details, completeness, GST/VAT rules, duplicate check, 3-way match against PO and goods receipt, approval policy, and decision. The result is **auto-approve**, **needs review** (reason, owner, next step) or **return to vendor**. Every stage and every human decision is written to an audit log. CLI for batch runs; Streamlit UI with a live run view, a review queue and a dashboard.

**Edge cases built in**

| Case | Behaviour |
|---|---|
| Split PO, over-billed (1,500 of 2,000 billed, invoice bills 700 more) | Review, procurement: 200 over, suggests paying 500 |
| Re-issued invoice under a new number | Review: same amount, PO and service period, 3 days apart. Next month's normal bill is not flagged |
| IGST charged inside Karnataka; GSTIN with a typo | Return to vendor: wrong tax head; checksum fails, so ITC is at risk |
| Bank account on invoice differs from master | Review, treasury: call vendor on the master number before paying |

Also: short receipt, price 8% over PO, missing PO inferred, scanned invoice, missing invoice number, unknown vendor, EU VAT instead of reverse charge, over the approval limit, TDS noted on the payable amount.

**Design choices.** Rules first, so it runs with no API key and every value traces back to a line of the PDF. The optional LLM only fills weak fields and its values sit below the auto-approve bar, so it can suggest but never approve. Confidence rises when amounts reconcile and drops when they do not. Reject only what the vendor must fix; everything else goes to review with an owner. All thresholds sit in one config file.

**Results (18 synthetic invoices, hand-written ground truth)**

| Test | Routes correct | Field accuracy | Wrong auto-approvals |
|---|---|---|---|
| Clean PDFs | 18/18 | 100% | 0 |
| Every invoice as a degraded scan, held-out seed | 13/18 | 97.0% | 0 |

Clean results only show the rules work as designed. On the scan test every miss went to a person, not to payment. My first scan test did approve a re-issued invoice (an OCR spacing issue). I fixed it, and the original report is kept in the repo. 38 automated tests.

**Not handled yet.** Real vendor layouts, e-invoice QR and live GSTIN/VIES checks, credit notes, partial approvals, multi-page tables, email intake, ERP connection.

**Week 2 with a real customer.** Two to three months of real invoices with AP's actual outcomes as ground truth. Shadow mode with a daily review of disagreements with the AP lead. Unwritten rules turned into config. Read-only connection to vendor master, POs and GRNs. Agreed measures: touchless share, zero wrong approvals before go-live, time in queue, top stop reasons.
