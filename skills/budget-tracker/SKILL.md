---
name: budget-tracker
description: Parse bank and credit-card statements (PDF/CSV), categorize every transaction, compare actual spend against the Monthly Budget Planning framework, and produce a discipline report with a budget dashboard. Use whenever the user shares a statement file, asks where their money went, wants a monthly spend review, asks about budget adherence, savings rate, or "how much did I spend on X".
argument-hint: "path(s) to statement PDF/CSV [+ month, e.g. 'May 2026']"
allowed-tools: Read, Write, Bash, Skill
---

# Budget Tracker

Read `references/reference.md` for the category taxonomy and the target allocation framework (mirrors the user's `Monthly Budget Planning.xlsx`).

No web access needed. Inputs are local statement files; the budget reference workbook is at `~/Downloads/Monthly Budget Planning.xlsx` (read actual targets from it when populated; otherwise use the framework percentages in reference.md and say so).

## Step 1 — Parse statements

- **CSV/XLSX**: parse directly with Python (pandas or csv stdlib). Bank exports vary; detect columns by header heuristics (date / narration / debit / credit / amount).
- **PDF**: extract via `pdfplumber` (install if missing) or invoke the `pdf` skill for stubborn/scanned files. Password-protected bank PDFs: ask the user for the password convention (usually PAN/DOB combos) rather than guessing.
- Normalize to one transaction table: `date, description, amount, direction, account`. De-duplicate CC-payment transfers between accounts so they're not counted as spend twice.

## Step 2 — Categorize

Map each transaction to the taxonomy in reference.md (UPI narrations: match merchant tokens — ZOMATO/SWIGGY → Dine & Entertainment, etc.). Anything unmatched goes to `UNCATEGORIZED` — list the top ones and ask the user to classify; remember their answers within the session and apply consistently. Never silently force a category. **Non-interactive runs** (user away / batch): keep them in `UNCATEGORIZED` as their own line in dashboard and verdict, with the top-5 listed in the report for later classification — do not block, do not guess.

## Step 3 — Compare vs budget

Aggregate per category and per bucket (Essential / Lifestyle / EMIs / Investments / Leftout) and compute each bucket's % of total inflow vs the target band. Flags:
- Bucket > target band → overspend flag with the top 3 driver transactions
- Investments below target → discipline gap (the framework treats investing as a bill, not a residual)
- Leftout negative → the month ran a deficit; identify whether it's one-off (annual premium) or structural

## Output

Render `assets/budget-dashboard.html` (bundled with this skill) (bucket gauges vs targets, category bars, top merchants, month-over-month if prior artifacts exist under `artifacts/budget/`), save to `artifacts/budget/<YYYY-MM>.html` (`paths.report_path("budget", "<YYYY-MM>", "html")`). In chat: savings rate (defined as (investments + leftout) / total inflow — state the formula), the single biggest leak, and one specific corrective action. Keep transaction-level data out of chat unless asked — it's sensitive; it lives in the artifact only.
