# AP invoice run run-20261112-013146-142

As-of date: 2026-11-12. LLM step: off. Invoices: 18. Inputs are synthetic test data.

| Route | Count |
|---|---|
| Auto-approve | 6 |
| Needs review | 7 |
| Reject (return to vendor) | 5 |

## Decisions

| File | Vendor | Invoice | Total | Route | Why |
|---|---|---|---|---|---|
| 01_sri_lakshmi_happy_intrastate.pdf | Sri Lakshmi Packaging Pvt Ltd | SLP/26-27/0418 | INR 30,385.00 | Auto-approve | all checks passed |
| 02_deccan_happy_interstate.pdf | Deccan Electricals & Components | DEC/2026/1187 | INR 1,74,640.00 | Auto-approve | all checks passed |
| 03_rheinwerk_happy_de.pdf | Rheinwerk Industrietechnik GmbH | RW-2026-00731 | EUR 3,145.17 | Auto-approve | all checks passed |
| 04_deccan_split_po_final_part.pdf | Deccan Electricals & Components | DEC/2026/1201 | INR 44,840.00 | Auto-approve | all checks passed |
| 05_sri_lakshmi_split_po_overbilled.pdf | Sri Lakshmi Packaging Pvt Ltd | SLP/26-27/0433 | INR 14,868.00 | Needs review | PO_QTY_EXCEEDED, GRN_SHORT |
| 06_nimbus_exact_duplicate.pdf | Nimbus Cloud Services LLP | NCS/INV/2026/0088 | INR 45,430.00 | Reject (return to vendor) | DUPLICATE_EXACT |
| 07_malnad_near_duplicate_reissued.pdf | Malnad Facility Services | MFS-1043 | INR 47,200.00 | Needs review | DUPLICATE_SUSPECTED |
| 08_malnad_wrong_tax_regime.pdf | Malnad Facility Services | MFS-1051 | INR 14,750.00 | Reject (return to vendor) | GST_REGIME_MISMATCH |
| 09_coastal_invalid_gstin.pdf | Coastal Freight Movers | CFM/2026/552 | INR 45,150.00 | Reject (return to vendor) | GSTIN_INVALID |
| 10_coastal_bank_details_changed.pdf | Coastal Freight Movers | CFM/2026/561 | INR 67,725.00 | Needs review | BANK_MISMATCH |
| 11_deccan_short_receipt.pdf | Deccan Electricals & Components | DEC/2026/1209 | INR 2,26,560.00 | Needs review | GRN_SHORT |
| 12_rheinwerk_price_variance.pdf | Rheinwerk Industrietechnik GmbH | RW-2026-00755 | EUR 1,735.02 | Needs review | PRICE_VARIANCE |
| 13_nimbus_no_po_inferred.pdf | Nimbus Cloud Services LLP | NCS/INV/2026/0112 | INR 45,430.00 | Auto-approve | PO inferred; all checks passed |
| 14_malnad_scanned_image_only.pdf | Malnad Facility Services | MFS-1058 | INR 14,750.00 | Auto-approve | read by OCR, amounts reconciled; all checks passed |
| 15_malnad_messy_no_invoice_number.pdf | Malnad Facility Services | (none) | INR 47,200.00 | Reject (return to vendor) | MISSING_INVOICE_NUMBER |
| 16_vandijk_vat_instead_of_reverse_charge.pdf | Van Dijk Precision B.V. | VDP-26-1187 | EUR 3,146.00 | Reject (return to vendor) | EU_REVERSE_CHARGE |
| 17_unknown_vendor.pdf | QuickFix Office Traders | QFT-2026-77 | INR 76,700.00 | Needs review | UNKNOWN_VENDOR, NO_PO_MATCH |
| 18_deccan_over_approval_limit.pdf | Deccan Electricals & Components | DEC/2026/1215 | INR 7,08,000.00 | Needs review | OVER_APPROVAL_LIMIT |

## What a person needs to do

**05_sri_lakshmi_split_po_overbilled.pdf** (Needs review, owner: Procurement)
- PK-CTN-STD: PO qty 2000, already billed 1500, so 500 left; this invoice bills 700 (200 over). Next step: Check for a PO amendment. Otherwise approve only 500 and ask for a credit note on the rest
- PK-CTN-STD: received 2000, billed so far 1500 + 700 on this invoice = 2200. Next step: Confirm the receipt. If 500 is right, pay for 500 and hold the rest

**06_nimbus_exact_duplicate.pdf** (Reject (return to vendor), owner: AP (send back to vendor))
- Invoice NCS/INV/2026/0088 from this vendor is already in the ledger (booked 2026-10-01, status paid). Next step: Do not pay again. Tell the vendor it was already processed

**07_malnad_near_duplicate_reissued.pdf** (Needs review, owner: AP)
- Looks like a re-issue of MFS-1042: same amount 47,200.00, 3 days apart, similar number (MFS-1042 vs MFS-1043), same PO KAV-PO-2026-1108, same service period (Oct 2026). Next step: Compare with MFS-1042 before paying. If it is a re-issue, reject it and ask the vendor for a credit note or confirmation

**08_malnad_wrong_tax_regime.pdf** (Reject (return to vendor), owner: AP (send back to vendor))
- Supplier and buyer are both in state 29, so CGST + SGST applies, but the invoice charges IGST. Next step: Return to vendor: wrong tax head. Paying it means the credit sits in the wrong ledger and the vendor has to fix it in their return

**09_coastal_invalid_gstin.pdf** (Reject (return to vendor), owner: AP (send back to vendor))
- GSTIN 33AAJFC6612R1ZA fails the checksum (last character should be 3). Next step: Return to vendor: input tax credit cannot be claimed against an invalid GSTIN

**10_coastal_bank_details_changed.pdf** (Needs review, owner: AP lead / Treasury)
- Bank account on invoice (77120055410983, KKBK0008811) differs from vendor master (ending 5678, IDIB000A012). Next step: Hold payment. Call the vendor on the phone number already in the master (not the one on the invoice) and confirm the change in writing before updating anything.

**11_deccan_short_receipt.pdf** (Needs review, owner: Warehouse / requester)
- EL-TRAY-300: received 270, billed so far 0 + 300 on this invoice = 300. Next step: Confirm the receipt. If 270 is right, pay for 270 and hold the rest

**12_rheinwerk_price_variance.pdf** (Needs review, owner: Buyer (procurement))
- RW-GBX-40: invoiced 48.60 vs PO 45.00 (+8.0%, tolerance 2%). Extra cost 108.00. Next step: Confirm an agreed price change and amend the PO, or ask the vendor for a credit note for the difference

**15_malnad_messy_no_invoice_number.pdf** (Reject (return to vendor), owner: AP (send back to vendor))
- No invoice number found on the document. Next step: Return to vendor: an invoice without a invoice number cannot be booked or claimed for input tax credit

**16_vandijk_vat_instead_of_reverse_charge.pdf** (Reject (return to vendor), owner: AP (send back to vendor))
- NL supplier charged 546.00 VAT on a B2B supply to our German entity. Cross-border B2B goods inside the EU are zero-rated and we self-account (reverse charge). Next step: Return to vendor: ask for a corrected invoice at 0% with the reverse charge note and both VAT IDs. Foreign VAT paid here is very hard to recover

**17_unknown_vendor.pdf** (Needs review, owner: Procurement)
- 'QuickFix Office Traders' (29AAQFQ1209D1Z9) is not in the vendor master. Next step: Do not pay. Check if this vendor should be onboarded and who ordered the goods.
- Cannot match to a PO without a known vendor

**18_deccan_over_approval_limit.pdf** (Needs review, owner: Finance manager)
- INR 7,08,000.00 is above the auto-approval limit of INR 5,00,000.00. Next step: Needs a second approval. Everything else is listed below for them
