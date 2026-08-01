# Phase 6 — deterministic analytics and grounded insights

## Acceptance contract

Phase 6 explains ledger changes with deterministic calculations before any future
language model summarizes them. The API compares the authenticated owner's current
local calendar month with the immediately preceding local month in one selected
currency.

Posted expenses and shared expenses contribute positive spending. Posted refunds
contribute negative spending. Income, transfers, pending transactions, voided
transactions, and other currencies do not contribute. Periods are half-open UTC
ranges derived from the owner's IANA timezone.

The comparison reports:

- current and previous spending, count, and average transaction size;
- absolute total, count, and average-size changes;
- category contribution deltas whose sum equals the total spending change; and
- grounded deterministic insights with the supporting transaction or obligation IDs.

The first insight rules are deliberately conservative:

- `spending_increase`: current spending is at least 25% above a positive previous
  baseline;
- `large_transaction`: a current expense is at least twice the median current
  positive expense, with at least three current expenses;
- `merchant_concentration`: one merchant supplies at least 50% of positive current
  spending;
- `possible_recurring`: the same merchant and exact amount appear at least three
  times in the last 12 months with consecutive gaps of 25–35 days; and
- `forgotten_debt`: an open or partially paid receivable is past its due date.

A zero previous baseline produces no percentage trend claim. Refunds may reduce
totals and category contributions but never become large-transaction or recurring
candidates. Cross-currency values are never combined.

This phase is read-only and requires no schema migration.
