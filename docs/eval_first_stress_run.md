# Evaluation report

All inputs are SYNTHETIC. I wrote the invoices, the ground truth and the rules, so the clean-PDF numbers mainly show the rules do what I designed them to do. They are not evidence of accuracy on real vendor invoices. The scanned stress test is a harder, more honest check of the extraction layer.

## Clean PDFs (as generated)

Invoices: 18. Routing accuracy: 18/18. Field accuracy overall: 198/198 (100.0%).

**Invoices auto-approved that should not have been: 0**

| Field | Correct | Accuracy |
|---|---|---|
| vendor_id | 18/18 | 100% |
| invoice_number | 18/18 | 100% |
| invoice_date | 18/18 | 100% |
| po_number | 18/18 | 100% |
| currency | 18/18 | 100% |
| net_amount | 18/18 | 100% |
| tax_amount | 18/18 | 100% |
| total_amount | 18/18 | 100% |
| supplier_tax_id | 18/18 | 100% |
| bank_account | 18/18 | 100% |
| line_count | 18/18 | 100% |

| Route | Precision | Recall | Predicted | Actual |
|---|---|---|---|---|
| AUTO_APPROVE | 100% | 100% | 6 | 6 |
| NEEDS_REVIEW | 100% | 100% | 7 | 7 |
| REJECT | 100% | 100% | 5 | 5 |

Confusion matrix (rows = expected, columns = predicted):

| expected \ predicted | AUTO_APPROVE | NEEDS_REVIEW | REJECT |
|---|---|---|---|
| AUTO_APPROVE | 6 | 0 | 0 |
| NEEDS_REVIEW | 0 | 7 | 0 |
| REJECT | 0 | 0 | 5 |

Expected reason codes found: 15/15

## Stress test: every invoice re-run as a degraded scan (OCR only)

Invoices: 18. Routing accuracy: 13/18. Field accuracy overall: 188/198 (94.9%).

**Invoices auto-approved that should not have been: 1**

| Field | Correct | Accuracy |
|---|---|---|
| vendor_id | 18/18 | 100% |
| invoice_number | 16/18 | 89% |
| invoice_date | 17/18 | 94% |
| po_number | 18/18 | 100% |
| currency | 14/18 | 78% |
| net_amount | 18/18 | 100% |
| tax_amount | 17/18 | 94% |
| total_amount | 17/18 | 94% |
| supplier_tax_id | 18/18 | 100% |
| bank_account | 18/18 | 100% |
| line_count | 17/18 | 94% |

| Route | Precision | Recall | Predicted | Actual |
|---|---|---|---|---|
| AUTO_APPROVE | 75% | 50% | 4 | 6 |
| NEEDS_REVIEW | 83% | 71% | 6 | 7 |
| REJECT | 62% | 100% | 8 | 5 |

Confusion matrix (rows = expected, columns = predicted):

| expected \ predicted | AUTO_APPROVE | NEEDS_REVIEW | REJECT |
|---|---|---|---|
| AUTO_APPROVE | 3 | 1 | 2 |
| NEEDS_REVIEW | 1 | 5 | 1 |
| REJECT | 0 | 0 | 5 |

Expected reason codes found: 14/15

Field errors:

- 02_deccan_happy_interstate.pdf: invoice_number expected 'DEC/2026/1187', got None
- 02_deccan_happy_interstate.pdf: currency expected 'INR', got None
- 03_rheinwerk_happy_de.pdf: currency expected 'EUR', got None
- 03_rheinwerk_happy_de.pdf: total_amount expected 3145.17, got None
- 12_rheinwerk_price_variance.pdf: invoice_number expected 'RW-2026-00755', got None
- 12_rheinwerk_price_variance.pdf: currency expected 'EUR', got None
- 15_malnad_messy_no_invoice_number.pdf: invoice_date expected '2026-11-09', got None
- 16_vandijk_vat_instead_of_reverse_charge.pdf: currency expected 'EUR', got None
- 17_unknown_vendor.pdf: tax_amount expected 11700.0, got 5850.0
- 18_deccan_over_approval_limit.pdf: line_count expected 1, got 0

Routing differences:

- 01_sri_lakshmi_happy_intrastate.pdf: expected AUTO_APPROVE, got NEEDS_REVIEW (LOW_CONFIDENCE)
- 02_deccan_happy_interstate.pdf: expected AUTO_APPROVE, got REJECT (MISSING_INVOICE_NUMBER)
- 03_rheinwerk_happy_de.pdf: expected AUTO_APPROVE, got REJECT (MISSING_TOTAL_AMOUNT)
- 07_malnad_near_duplicate_reissued.pdf: expected NEEDS_REVIEW, got AUTO_APPROVE (no reasons)
- 12_rheinwerk_price_variance.pdf: expected NEEDS_REVIEW, got REJECT (MISSING_INVOICE_NUMBER)
