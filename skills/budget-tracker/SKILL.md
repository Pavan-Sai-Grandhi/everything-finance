---
name: budget-tracker
description: Parse bank and credit-card statements (PDF/CSV), categorize every transaction against a durable merchant memory, detect recurring/subscription spend, compare actual spend against the Monthly Budget Planning framework, and produce a discipline report with a budget dashboard. Use whenever the user shares a statement file, asks where their money went, wants a monthly spend review, asks about budget adherence, savings rate, subscriptions/recurring charges, or "how much did I spend on X". Also the cashflow leg other skills consume via `quick`.
argument-hint: "path(s) to statement PDF/CSV [+ month, e.g. 'May 2026'] [+ quick|deep]"
allowed-tools: Read, Write, Bash, Skill
---

# Budget Tracker

Read `references/reference.md` for the category taxonomy, the durable-map layering, the recurring-detection rules, and the target allocation framework (mirrors the user's `Monthly Budget Planning.xlsx`).

No web access needed. Inputs are local statement files; the budget reference workbook is at `~/Downloads/Monthly Budget Planning.xlsx` (read actual targets from it when populated; otherwise use the framework percentages in reference.md and say so).

Two deterministic scripts do the categorization and recurring detection so the numbers are tested, not eyeballed — call them, don't re-implement their logic:
- `scripts/categorize.py` — durable merchant map + taxonomy → categorized transactions + UNCATEGORIZED residue.
- `scripts/recurring.py` — recurring charges across current + prior months, with cadence and new/creep/dormant flags.

## Modes

- **`quick`** — the cheap cashflow read other skills (wealth-manager) consume. Parse → categorize (durable map) → bucket-vs-target adherence → recurring total, returned as a **compact digest** (see *Cashflow-leg digest*). No HTML render, no chat essay.
- **`deep`** (default on direct invocation) — the full review: parse → categorize → recurring detection → bucket comparison → `budget-dashboard.html` → chat summary.

## Step 1 — Parse statements

- **CSV/XLSX**: parse directly with Python (pandas or csv stdlib). Bank exports vary; detect columns by header heuristics (date / narration / debit / credit / amount).
- **PDF**: extract via `pdfplumber` (install if missing) or invoke the `pdf` skill for stubborn/scanned files. Password-protected bank PDFs: ask the user for the password convention (usually PAN/DOB combos) rather than guessing.
- Normalize to one transaction table: `date, description, amount, direction, account`. De-duplicate CC-payment transfers between accounts so they're not counted as spend twice.
- A corrupt/unreadable file or section → report which file/section failed, process the rest, never silently drop transactions.

## Step 2 — Categorize (durable map first)

Write the normalized table to a temp JSON and run `python3 scripts/categorize.py --txns <file>` (it loads `paths.merchant_map_path()` = `artifacts/budget/merchant-map.json` automatically). Resolution order per transaction: **durable merchant map → reference.md taxonomy → UNCATEGORIZED**. The map is keyed by normalized merchant token (`ZOMATO`, `SWIGGY`), so UPI/POS/handle variants collapse to one rule and corrections persist across months.

UNCATEGORIZED handling:
- **Interactive**: list the top UNCATEGORIZED merchants and ask the user to classify. Record each answer with `python3 scripts/categorize.py --learn --merchant "<narration>" --category "<Category>"` so it sticks — UNCATEGORIZED shrinks month over month. Never silently force a category.
- **Non-interactive** (user away / batch): keep them in `UNCATEGORIZED` as their own line in the dashboard and verdict, top-5 listed for later classification — do not block, do not guess.
- **First run / missing map**: behaves as taxonomy-only, then starts building the map.

## Step 3 — Recurring / subscription detection

Concatenate the current transactions with prior months' (from `artifacts/budget/`) into one JSON and run `python3 scripts/recurring.py --txns <file> [--as-of <YYYY-MM-DD>]`. It returns the committed **recurring ₹/month**, the subscription/EMI/membership list (cadence, amount, months observed), and **new / price_creep / dormant** flags. Cite amounts with the months they were observed in. With no prior months it runs on the current statements only and labels confidence **low** (cadence inferred from a single period) — say so.

## Step 4 — Compare vs budget

Aggregate per category and per bucket (Essential / Lifestyle / EMIs / Investments / Leftout) and compute each bucket's % of total inflow vs the target band. Flags:
- Bucket > target band → overspend flag with the top 3 driver transactions
- Investments below target → discipline gap (the framework treats investing as a bill, not a residual)
- Leftout negative → the month ran a deficit; identify whether it's one-off (annual premium) or structural

## Output — `deep`

Render `assets/budget-dashboard.html` (bundled with this skill: bucket gauges vs targets, category bars, top merchants, the committed-recurring-spend panel, month-over-month if prior artifacts exist under `artifacts/budget/`), save to `artifacts/budget/<YYYY-MM>.html` (`paths.report_path("budget", "<YYYY-MM>", "html")`). In chat: savings rate (defined as (investments + leftout) / total inflow — state the formula), the single biggest leak, and one specific corrective action. Keep transaction-level data out of chat unless asked — it's sensitive; it lives in the artifact only.

## Output — `quick` (cashflow-leg digest)

Return only the compact digest the caller consumes — no HTML, no transaction detail:

```
<!-- cashflow-block
savings_rate: <pct>            # (investments + leftout) / total inflow
buckets: { Essential: {actual_pct, target, status}, Lifestyle:{...}, EMIs:{...}, Investments:{...} }
biggest_leak: <category> ₹<amount>
recurring_monthly: ₹<total committed recurring/month>
target_source: workbook | framework
gaps: [ ... ]                  # e.g. "UNCATEGORIZED ₹X across N txns", "no prior months"
month: <YYYY-MM>
-->
```

State whether targets came from the workbook or the framework percentages. If the workbook is absent, use framework percentages and label them as such. This digest shape is the leg contract in `lib/contracts.md`; keep it in sync.
