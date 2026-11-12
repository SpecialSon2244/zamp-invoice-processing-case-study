# Decisions and why

A short list so I can explain each choice. Format: what I decided, why, and what I gave up.

## Scope

1. **PS-1, invoice processing.** Concrete inputs, checkable rules, and mistakes that cost real money,
   so "correct" is easy to define and measure. Gave up: the open-ended research angle of PS-3.
2. **Indian GST first, EU VAT second.** GST tax-head and GSTIN checks are a big part of manual AP work
   in India. EU invoices force a second tax system and a second number format (3.145,17) through the
   same process. Gave up: depth in either; I check format and logic, not live registration status.
3. **Synthetic data, clearly labelled.** The brief allows it, and I needed to control the edge cases
   and know the right answer for every field. Every PDF says "SYNTHETIC TEST DATA" in the footer.
   Gave up: the mess of real layouts, which is why the README says the numbers prove the rules, not
   real-world accuracy.
4. **Assumption: one buyer group with an Indian and a German entity.** The bill-to tax ID decides which
   rule set applies. Other assumptions are below.

## Reading the invoice

5. **pdfplumber for the text layer, RapidOCR only when a page has no text.** Text layers are exact and
   free; OCR is slower and makes mistakes, so it is only used when needed. RapidOCR installs with pip
   (no system Tesseract), so the demo runs on any laptop.
6. **Labelled regex patterns, not one template per vendor.** Labels like "Invoice No", "Bill No",
   "Tax Invoice No." cover many layouts with one rule. Separators are loose on purpose because OCR
   reads ":" as ";" or ".". Gave up: precision on layouts with no labels at all.
7. **Day-first dates.** India and the EU both write 05/11/2026 as 5 November. Gave up: US-format
   invoices would be misread; I would add a per-vendor date format if that came up.
8. **Number parsing by the last separator.** If the last "." or "," is followed by exactly two digits,
   it is the decimal point. This handles 1,74,640.00, 174,640.00 and 3.145,17, and even OCR's 2.643.00.

## Confidence

9. **Simple, explainable confidence instead of a model probability.** Labelled match 0.95, pattern-only
   0.75, LLM 0.80, OCR scaled by the OCR engine's score for that line. An AP lead can understand why a
   field is 0.81.
10. **Cross-checks move the score.** If line items sum to net and net plus tax equals total, three
    separate reads agree, so amount confidence goes up. If they disagree, it drops below the review bar.
    This is why a clean scan can be auto-approved but a smudged one cannot.
11. **0.85 threshold on critical fields** (invoice number, date, net, tax, total, supplier tax ID). A
    labelled text read passes, a clean OCR read just passes, anything weaker goes to a person.

## The LLM

12. **Optional and off by default.** The process has to run live in the interview with no key and no
    network. Rules are cheaper, faster, deterministic and auditable.
13. **The LLM only fills weak fields and cannot approve.** Its values get 0.80 confidence, below the
    0.85 bar, and still go through every rule. So an LLM-read critical field always ends with a person.
    Gave up: some touchless rate on messy invoices, in exchange for never paying on a guess.
14. **Any OpenAI-compatible endpoint via environment variables, called with plain urllib.** No SDK lock-in,
    no extra dependency. If the call fails, the run carries on with rule values and logs why.

## Checks and routing

15. **Three routes, and reject means "only the vendor can fix this".** Wrong tax head, invalid GSTIN,
    missing invoice number, foreign VAT on reverse charge, exact duplicate. Everything that needs our own
    judgement is review. This matches how AP teams actually work: send back vs escalate inside.
16. **Reject beats review beats approve, and all reasons are kept.** A rejected invoice also lists the
    review issues, so when the vendor sends a corrected one nobody is surprised.
17. **Every review reason has an owner and a next step.** Price variance goes to the buyer, short
    receipt to the warehouse, bank change to treasury, over-limit to the finance manager. A queue that
    just says "exception" does not save anyone time.
18. **Missing field on a scan is review, not reject.** Added after the first stress test: on a scan you
    cannot tell "the vendor left it out" from "OCR missed it", so a person looks first.

## GST and VAT

19. **GSTIN checksum, format and state code.** A one-character typo in a GSTIN means no input tax
    credit. The checksum catches it without any API.
20. **CGST + SGST vs IGST from supplier state vs place of supply** (our state, 29 Karnataka). Wrong
    tax head goes back to the vendor; paying it puts the credit in the wrong ledger.
21. **GST slabs 0, 3, 5, 18, 40 (after the September 2025 change), configurable.** An unusual rate
    goes to the tax team, not to reject, because special rates exist.
22. **TDS is a note, not a block.** The process computes TDS on the taxable value (excluding GST) at
    the rate in the vendor master and shows the net payable. Which section applies is the tax team's
    decision, so the rate lives in the master, not in my code.
23. **EU cross-border B2B must be 0% with reverse charge.** Foreign VAT charged by mistake is very hard
    to recover, so it goes back to the vendor.

## Duplicates

24. **Normalise invoice numbers before comparing.** "NCS/INV/2026/0088" and "ncs-inv-2026-88" are the
    same invoice.
25. **Near-duplicate = same vendor, total within 0.5%, within 20 days, and either a similar number or
    the same PO, unless the service periods differ.** This catches the re-issued invoice and does not
    flag the normal monthly invoice for the next month. Gave up: a re-issue more than 20 days later
    would be missed; the window is a setting.
26. **Earlier invoices in the same run count too.** Otherwise two copies in one batch would both pass.

## Matching

27. **Match lines by item code first, then by description similarity (0.6 or more).** Codes are exact
    when present; descriptions catch the vendors that do not print our codes.
28. **Running count of billed quantity per PO line** from the ledger plus this run. This is what catches
    split POs that are over-billed. Received quantity comes from GRNs or service entry sheets.
29. **Price tolerance 2% above PO, any amount below is fine.** Small rounding or freight differences
    should not stop an invoice; 8% should. Below-PO prices only help us.
30. **Infer a missing PO only when exactly one open PO for that vendor fits** every line and the remaining
    quantity. Zero or several candidates go to procurement.
31. **Approval limit INR 5 lakh / EUR 10,000.** Even a perfect match above the limit needs a second person;
    that is a control, not a data problem.

## Product and evaluation

32. **CLI first, UI second.** The CLI runs the whole batch with one command and is what the tests use.
    The Streamlit UI shows the same stages live, the review queue and the history, which the brief asks for.
33. **Audit log of every stage and every human decision** in SQLite and a JSONL file. A human decision
    needs a note before it is saved.
34. **Ground truth written by hand before running the pipeline**, per field and per route.
35. **Main metric: auto-approved when it should not have been.** Then routing precision and recall, then
    field accuracy. In AP a wrong approval costs money; a wrong review costs a few minutes.
36. **OCR stress test with a held-out seed.** I used one noise seed to find and fix parser problems and
    kept a second seed for one run after the fixes, so I have at least one number I did not tune for.
37. **Each run starts from the ledger file and does not write back to it.** Invoices accepted earlier in
    the same run count for duplicates and PO quantities, but approved invoices are not added to
    `ap_ledger.csv`. That keeps the demo repeatable: running invoice 01 twice in two separate runs will
    not flag a duplicate. The duplicate demo uses 06, which is already in the ledger. In production,
    approvals would post to the ledger.
38. **Business date is fixed (`--as-of`)** so results are the same whichever day the demo runs.
