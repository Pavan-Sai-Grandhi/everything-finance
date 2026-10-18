---
name: budget-tracker
description: Parse bank and credit-card statements (PDF/CSV), categorize every transaction against a durable merchant memory, detect recurring/subscription spend, compare actual spend against the monthly budget framework, and produce a discipline report with a budget dashboard. Use whenever the user shares a statement file, asks where their money went, wants a monthly spend review, asks about budget adherence, savings rate, subscriptions/recurring charges, or "how much did I spend on X". Also the cashflow leg wealth-manager consumes via `quick`.
argument-hint: "path(s) to statement PDF/CSV [+ month, e.g. 'May 2026'] [+ quick|deep]"
allowed-tools: Read, Write, Bash, Skill, mcp__finance-personal__categorize_transactions, mcp__plugin_everything-finance_finance-personal__categorize_transactions, mcp__finance-personal__learn_merchant, mcp__plugin_everything-finance_finance-personal__learn_merchant, mcp__finance-personal__detect_recurring, mcp__plugin_everything-finance_finance-personal__detect_recurring
---

# Budget Tracker

The month's spend, judged against a budget. The inputs are the user's own statement files, so no
market data is involved. The user's budget workbook sets the targets when supplied; otherwise the
framework bands are used and labelled as such.

**Method:** `methods/personal-finance.md` (§ Budget buckets, § Judging a month).

## Modes

- **`deep`** (default on direct invocation): parse, categorize, detect recurring spend, compare
  against the buckets, render the dashboard, summarise in chat.
- **`quick`**: the cashflow read wealth-manager consumes. Parse, categorize, bucket adherence and
  the recurring total, returned as the `cashflow-block` digest (`finance/contracts.md` →
  *Convention: cashflow-leg digest*). No HTML, no transaction detail, no chat essay.

## Workflow

1. **Parse the statements** into one table of `date, description, amount, direction, account`.
   CSV or XLSX: read it directly, detecting columns from the headers. PDF: extract with
   `pdfplumber`; a statement that yields no rows is probably scanned, so ask for a CSV export
   rather than guessing at OCR. For a password-protected bank PDF, ask the user for the password
   convention. Remove card-bill payments between the user's own accounts so they are not counted
   twice. Report any unreadable file or section and process the rest; never drop transactions
   silently. Write the table to a JSON file under the artifacts `tmp/budget/` directory.
2. **Categorize**: `categorize_transactions(transactions=<file>)`. It resolves each row through
   the durable merchant map, then the taxonomy, then UNCATEGORIZED.
   - With the user present, list the top uncategorized merchants and ask; record each answer with
     `learn_merchant(merchant=<narration>, category=<category>)` so it sticks next month. Never
     force a category.
   - Without the user, keep UNCATEGORIZED as its own line, top five listed for later.
   - An unreadable map is a gap and the taxonomy is used; `learn_merchant` refuses to write until
     the file is repaired. Never replace it with an empty map.
3. **Recurring spend**: combine this month's table with prior months' from `artifacts/budget/`,
   dropping rows after `as_of` and duplicate imports by transaction id (two purchases with the
   same merchant, date and amount are not duplicates), then call
   `detect_recurring(transactions=<file>, as_of=<YYYY-MM-DD>)`. Cite every amount with the months
   it was seen in, carry its confidence, and keep single-charge candidates out of the total. The
   total is what was observed, not a contractual commitment.
4. **Compare against the budget.** Check statement coverage and inflows first: a credit can be a
   transfer, a refund or a loan, so it is not automatically income. Match refunds to the original
   expense where possible and list unmatched credits as gaps. ATM cash is untracked spend; do not
   also count purchases made from it. Percentages use verified household income; without it,
   savings rate and adherence are unassessed. Then flag per the method: a bucket over its band
   (with the top three driver transactions), investments below target, a negative leftout.

Carry every tool gap into the report. An incomplete month is not a balanced budget.

## Output: `deep`

Fill `assets/budget-dashboard.html` and save it to `artifacts/budget/<YYYY-MM>.html`. HTML-escape
every filled value, use only the class values the template documents, and keep style values
finite. Set `SAVINGS_RATE_DISPLAY` to a percentage or "Unassessed", omit a gauge whose
denominator or target is missing, carry gaps into `DATA_GAPS`, and show single-charge recurring
equivalents as "—".

In chat: the savings rate, with its formula ((investments + leftout) / total inflow), the single
biggest leak, and one specific corrective action. Transaction-level data is sensitive: it lives in
the artifact, not the chat.
