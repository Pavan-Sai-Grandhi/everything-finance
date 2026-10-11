---
name: budget-tracker
description: Parse bank and credit-card statements (PDF/CSV), categorize every transaction against a durable merchant memory, detect recurring/subscription spend, compare actual spend against the Monthly Budget Planning framework, and produce a discipline report with a budget dashboard. Use whenever the user shares a statement file, asks where their money went, wants a monthly spend review, asks about budget adherence, savings rate, subscriptions/recurring charges, or "how much did I spend on X". Also the cashflow leg other skills consume via `quick`.
argument-hint: "path(s) to statement PDF/CSV [+ month, e.g. 'May 2026'] [+ quick|deep]"
allowed-tools: Read, Write, Bash, Skill
---

# Budget Tracker

Read `references/reference.md` for the category taxonomy, the durable-map layering, the recurring-detection rules, and the target allocation framework (optional fallback heuristics; user-supplied targets take precedence).

**No network source at all** — inputs are the user's own local statement files, so this skill calls no data tool. Use the budget workbook the user supplies, if any; do not assume a private Downloads file exists or has been read. Otherwise label the framework percentages in reference.md as fallback comparisons.

Two deterministic scripts do the categorization and recurring detection — call them, don't re-implement their logic:
- `scripts/categorize.py` — durable merchant map + taxonomy → categorized transactions + UNCATEGORIZED residue.
- `scripts/recurring.py` — recurring charges across current + prior months, with cadence and new/creep/dormant flags.

## Modes

- **`quick`** — the cheap cashflow read other skills (wealth-manager) consume. Parse → categorize (durable map) → bucket-vs-target adherence → recurring total, returned as a **compact digest** (see *Cashflow-leg digest*). No HTML render, no chat essay.
- **`deep`** (default on direct invocation) — the full review: parse → categorize → recurring detection → bucket comparison → `budget-dashboard.html` → chat summary.

## Step 1 — Parse statements

- **CSV/XLSX**: parse directly with Python (pandas or csv stdlib). Bank exports vary; detect columns by header heuristics (date / narration / debit / credit / amount).
- **PDF**: extract via `pdfplumber` (install if missing); if it yields no rows the statement is likely scanned, so ask for a CSV export rather than guessing at OCR. Password-protected bank PDFs: ask the user for the password convention (usually PAN/DOB combos) rather than guessing.
- Normalize to one transaction table: `date, description, amount, direction, account`. De-duplicate CC-payment transfers between accounts so they're not counted as spend twice.
- A corrupt/unreadable file or section → report which file/section failed, process the rest, never silently drop transactions.

## Step 2 — Categorize (durable map first)

Write the normalized table to a temp JSON and run `python3 <plugin>/skills/budget-tracker/scripts/categorize.py --txns <file>` (it loads `paths.merchant_map_path()` = `artifacts/budget/merchant-map.json` automatically). It resolves **durable merchant map → taxonomy → UNCATEGORIZED**; reference.md carries the tokenizer and the layering.

UNCATEGORIZED handling:
- **Interactive**: list the top UNCATEGORIZED merchants and ask the user to classify. Record each answer with `python3 <plugin>/skills/budget-tracker/scripts/categorize.py --learn --merchant "<narration>" --category "<Category>"` so it sticks — UNCATEGORIZED shrinks month over month. Never silently force a category.
- **Non-interactive** (user away / batch): keep them in `UNCATEGORIZED` as their own line in the dashboard and verdict, top-5 listed for later classification — do not block, do not guess.
- **First run / missing map**: behaves as taxonomy-only, then starts building the map.
- **Invalid/unreadable map**: categorization reports a gap and uses taxonomy without altering saved rules. Learning fails safely; preserve and repair the existing file before adding corrections. Never replace it with an empty map to clear the error.
- Carry the scripts' `gaps` into the report. Invalid transaction rows are excluded explicitly; do not call an incomplete month a balanced budget.

## Step 3 — Recurring / subscription detection

Concatenate the current transactions with prior months' (from `artifacts/budget/`) into one JSON and run `python3 <plugin>/skills/budget-tracker/scripts/recurring.py --txns <file> [--as-of <YYYY-MM-DD>]`. It returns the committed **recurring ₹/month**, the subscription/EMI/membership list (cadence, amount, months observed) and the **new / price_creep / dormant** flags, per the detection rules in reference.md. Cite every amount with the months it was observed in, and carry its confidence and `gaps` through. A single charge is an unconfirmed candidate with null cadence/monthly equivalent and is excluded from the total. The total covers observed active patterns, not verified contractual obligations. Exclude post-`as_of` transactions and deduplicate overlapping imports by transaction identity before concatenating; do not deduplicate different purchases merely because merchant/date/amount match.

## Step 4 — Compare vs budget

Reconcile statement coverage and inflows first. Credits can be own-account transfers, refunds or loan proceeds; they are not automatically income. Match refunds to the original expense where evidence permits and show unresolved credits as gaps. ATM withdrawals represent cash moved out of the account, with final spending untracked; do not count both a withdrawal and its documented cash purchases. Use verified positive household income for percentages; missing/zero income leaves savings rate and adherence unassessed.

Aggregate per category and per bucket (Essential / Lifestyle / EMIs / Investments / Leftout) and compute each bucket's % of verified inflow vs the declared target band. Comparisons to fallback bands are descriptive, not personalized investment instructions. Flags:
- Bucket > target band → overspend flag with the top 3 driver transactions
- Investments below target → discipline gap (the framework treats investing as a bill, not a residual)
- Leftout negative → the month ran a deficit; identify whether it's one-off (annual premium) or structural

## Output — `deep`

Render `assets/budget-dashboard.html` (bundled with this skill: bucket gauges vs targets, category bars, top merchants, the committed-recurring-spend panel, month-over-month if prior artifacts exist under `artifacts/budget/`), save to `artifacts/budget/<YYYY-MM>.html` (`paths.report_path("budget", "<YYYY-MM>", "html")`). HTML-escape all filled text, constrain class fields to the template's documented choices, and use finite numeric style values. Set `SAVINGS_RATE_DISPLAY` to a formatted percentage or “Unassessed”; omit gauges when their denominator or target is missing. Carry script gaps into `DATA_GAPS` and leave unconfirmed recurring equivalents as “—”. In chat: savings rate (defined as (investments + leftout) / total inflow — state the formula), the single biggest leak, and one specific corrective action. Keep transaction-level data out of chat unless asked — it's sensitive; it lives in the artifact only.

## Output — `quick` (cashflow-leg digest)

Return only the compact **`cashflow-block`** digest, whose shape and field semantics `finance/contracts.md` owns (*Convention: cashflow-leg digest*) — no HTML, no transaction detail, no chat essay.
