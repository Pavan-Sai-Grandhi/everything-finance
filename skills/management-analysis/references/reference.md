# Management quality — integrity & skill (self-contained method)

Distilled from a practitioner management-analysis framework (Money Purse "select stocks like an expert" series, Parts 2A/2B), which itself builds on **Vijay Malik's** integrity checklists and **Philip Fisher's** dictum that ~90% of company analysis effort belongs on management, ~9% on the industry, ~1% elsewhere. Two companies with the *same* opportunity diverge almost entirely on management's **integrity** (will they treat minority shareholders honestly?) and **skill** (can they actually grow the business?).

This is **subjective by nature** — there are no fixed ratios. The percentages below are guide-rails, not bright lines; what you are really judging is **intention**. A small breach of a threshold with a clean intention is fine; a pattern that reveals intent to enrich insiders at minority-shareholders' expense is disqualifying even if no single number looks extreme. Read for the *pattern*, not the point reading.

> Companies named in the source material (Prince Pipes, Future Retail, Eicher, Pidilite, Happiest Minds, Cupid, etc.) are **teaching examples only — not buy/sell calls**, and the data may be dated. Re-verify on current filings before relying on any of it.

## Pillar 1 — INTEGRITY (a gate, checked first)

Integrity is screened **before** skill. A *skilled but dishonest* management is more dangerous than an unskilled honest one — the more capable they are, the more efficiently they can siphon. Analogy from the source: you won't put your cash and gold in a car driven through a forest by a driver who pockets small things. Any hard integrity failure → **AVOID**, regardless of how good the business or the skill looks.

**Each of the seven checks is scored separately as PASS / FLAG / FAIL / NOT-CHECKED**, and the gate is the aggregate: `FAIL` if any check failed; `PASS` only when all seven were performed; otherwise **`PASS (partial, k of 7)`**, which downstream weighs as uncertainty, not as a cleared gate. A check you could not source is `NOT-CHECKED` — never a silent PASS, because PASS is what makes the rest of the analysis count.

1. **Managerial remuneration vs profit.** Compute it, don't eyeball it: `finance/compute/governance.py` `remuneration_check(total_remuneration, net_profit, managing_directors)` returns the ratio against the ~5% norm and the Companies Act s.197 ceiling (11% total, 5% for a single MD/WTD, 10% for more than one), and `NOT-CHECKED` when the annual report does not disclose at that granularity. Honest managements keep total promoter/KMP pay **below the MCA-prescribed limit** and typically **under ~5% of net profit** (₹5 Cr on ₹100 Cr PAT). Read the pattern the arithmetic cannot see:
   - Pay **rising while profits fall**.
   - Pay **exceeding the MCA limit** → strong avoid.
   - **Relatives padded onto the payroll** at identical/round salaries (e.g. several "VPs" all on the exact same ₹55.2 L, all related to the promoter) — a route to extract cash around the limit. *Source: annual report "remuneration of directors / KMP" and the related-party remuneration notes; compare across 2–3 years.*

2. **Related-party transactions (RPTs).** RPTs are **normal and not wrong per se** — good companies have them. What matters is **abnormality**: loans to promoter entities **below market rate**, goods/services **bought from related companies above market rate**, sponsorships/deposits to relatives' firms. The mechanism: a listed company's profit is *shared* with public shareholders (promoter keeps maybe 50–70%), but an unlisted promoter-owned company is **100% the promoter's** — so siphoning value from the listed co into the unlisted one enriches insiders at minority-holders' expense. *Source: annual report "related party transactions" note — read the amounts, rates, and counterparties. RPTs cover directors, KMP, their relatives, holding and subsidiary companies.*

3. **Criminal / regulatory track record.** Would you start a business with a partner who has a criminal record? As a shareholder you *are* a (minority) partner. Check the promoter and company for **criminal cases and regulator warning letters (SEBI/RBI)**. This is a **defined query set, not a look around**: the company name, and each named promoter and KMP from the board profiles, each crossed with `SEBI order`, `fraud`, `investigation`, `penalty`, `resignation`. Report the set you ran; absence of hits across a stated set is a finding, absence after two ad-hoc searches is not. For IPOs read the RHP's litigation/regulatory section. A genuine criminal record or pattern of regulator action → avoid.

4. **Media-savvy & share-price obsession.** A promoter's job is to run the business. Flags:
   - Frequent **business-TV appearances announcing sector entries** (pharma boom → "we're entering pharma"; later an insurance boom → "we're entering insurance") with **no follow-through** = share-price manipulation, not strategy.
   - **Page-3 / party-circuit** prominence over business focus (the source quotes Nilesh Shah: he reads page 3 to find companies *to sell* — promoters who party more than they work tend to destroy businesses).
   - **Annual-report management commentary over multiple years that only discusses current fads** with no durable long-term plan.
   - **Were past plans executed?** This is the sub-check that separates a strategy from a headline, and you judge it yourself from the **multi-year MD&A** — `get_documents(symbol, annual_reports=3)` returns each report's text. Take the forward commitments management made in the earliest report you hold (a capacity, a market entry, a margin, a debt-reduction target, a launch date), then look for what the later reports say happened. **What counts as evidence:** a *specific, dated* prior commitment set against a *specific* later outcome, both quoted from the reports — "FY23 MD&A promised the Gujarat line by FY25; FY25 MD&A does not mention it and capex fell". A vague aspiration ("we will pursue growth") is not a commitment and cannot be scored either way; say so rather than manufacture a miss. A pattern of announced-then-abandoned plans is a FLAG, and with the TV-announcement pattern above it becomes share-price management, not strategy. Silence about a plan that quietly disappeared is itself evidence — of the ego problem in check 6.

5. **CFO & auditor churn / fees.** The CFO and auditors know the *real* financial state.
   - **Resignations within 1–2 years**, repeatedly → red flag.
   - **Auditor fee jumping abnormally** (e.g. ₹10 L → ₹50 L year-on-year) or **out of line with peers by size** (a ₹100 Cr-mcap firm paying the same audit fee as a ₹1 L Cr-mcap firm) → possible manipulation. Fee rising roughly with inflation is fine. `governance.auditor_fee_check(fees, revenues, profits)` reads the fee against the business it audits and calls out a fee rising into a profit collapse. *Source: AR "payment to auditors" note (`outline.auditor_remuneration`), tracked over 5–10 years and benchmarked to peers.*

6. **Ego — unwillingness to own mistakes, and evasion under questioning.** Managements that **never admit errors** are dangerous. Example pattern: a serial-acquirer that overpaid, then **wrote off goodwill blaming COVID** (when the year had only days of COVID impact) rather than admitting the acquisitions were expensive. Avoid managements that rationalise instead of accepting and correcting mistakes. *Source: AR notes/impairments.*
   - **Which questions did management dodge?** Read the **concall Q&A as asked and answered** — `get_documents` returns the transcript's text, and the transcript is the only place the question survives alongside the answer. Pair each analyst question with the reply and judge whether it was answered. **What counts as evidence:** a specific question quoted, its reply quoted, and the gap named — a number asked for and not given, a redirect to an unrelated metric, "we don't guide" on a figure they guided on last quarter, an answer that runs long and says nothing. **What does not:** a question management legitimately cannot answer (a pending regulatory matter, a signed NDA, price-sensitive information they are barred from disclosing) — note it and move on. One deflection is a bad day; **the same question dodged across consecutive calls is a pattern**, and a dodge on the topic the integrity checks already flagged (an RPT, the auditor change, the pledge) is the strongest single governance signal a transcript can carry.

7. **Promoter pledging.** Pledging is **not inherently bad** — even good promoters pledge when they need funds. Judge the **reason** and the **percentage**: low single digits (3–5%) is usually fine; **abnormal pledging** (e.g. ~69%) can hand the company to lenders on a margin call (the source cites Future group pre-collapse). *Source: `get_company_fundamentals(sections=['shareholding'])` carries `Promoter Pledge (% of promoter holding)` over six quarters — note the denominator is the promoter stake, not the share capital. Cross-read `get_shareholding`'s NSE pledge rows (a separate endpoint that is often empty — an empty list is UNKNOWN, never nil pledge) and the AR/SHP filing for the **reason**, which no feed carries.*

**Skill-builders for integrity:** Vijay Malik's blogs (deep RPT/remuneration forensics); Moneylife / Sucheta Dalal exposés of dishonest promoters.

## Pillar 2 — SKILL (graded for integrity-clean managements)

Skilled management can turn a struggling company around (the source's example: Siddhartha Lal at Eicher — shut loss-making commercial-vehicle lines, concentrated on Royal Enfield, made it a multibagger). Among honest managements, grade capability:

1. **Qualification & experience.**
   - **Relevant education** to the sector. First-generation founders usually understand their industry end-to-end; be cautious when a **second-generation heir's background is unrelated** (e.g. an IT-trained child running a pharma family business).
   - **Years in the sector**: 10–15+ years means they've lived a **full up-and-down cycle** and know how to handle a downturn. *Source: AR board/KMP profiles, company "About".*

2. **Mindset — growth vs comfort zone.** Early-stage managements usually have a growth mindset; after some success many settle into a comfort zone, and a stagnant company means a stagnant investment. Integrity check 4's plan-execution read already establishes *whether* they executed; here you read the same MD&A for **ambition** — is there a forward plan at all, is it bigger than last year's, does the concall carry capital plans and appetite or only maintenance? Executed-but-unambitious is the comfort zone; ambitious-but-unexecuted is the integrity flag. *Source: multi-year AR MD&A + the concall transcript.*

3. **Capital allocation.** What do they do with retained earnings (profit kept after dividends)?
   - Retained earnings should compound at **≥ ~12–14%**. If the business only earns **5–6% on reinvested capital, it's better off paying dividends** (shareholders would do better even in an FD). Test ≈ Buffett's "**₹1 retained should create ≥ ₹1 of market value**", or ROE on *incremental* retained earnings.
   - Good long-term allocators (source cites Nestlé, HDFC) compounded by deploying retained earnings well. *Source: concall capital-allocation commentary + AR; compute return on retained earnings over a cycle.*

4. **Succession plan.** A promoter aged **60–70 needs a credible successor** — either a **professionalised management** or a **skilled family member**. Good: Pidilite grooming Bharat Puri (board → management over 2–3 years). Concern: an old promoter with **no plan** (the source cites Cupid at the time, and Happiest Minds' Ashok Soota succession question at IPO). **No succession plan = real risk.** *Source: AR, concalls, board structure.*

## Verdict — how to combine

1. **Integrity is a hard gate.** Any of these → **management grade = AVOID** no matter the skill: money-siphoning RPTs, a genuine criminal/regulatory record, remuneration above the MCA limit (or pay rising as profit falls), abnormal pledging with no sound reason, demonstrable dishonesty. Softer integrity concerns (media-savvy, ego, mild auditor-fee drift) are **FLAGS** that lower confidence, not automatic disqualifiers — weigh the pattern.
2. **Grade skill only for integrity-clean managements**, across the four skill checks.

Every judgement cites its source (AR page/note, concall transcript line, exchange filing, dated interview). "Good management" with no evidence is a defect.

## Evidence standard

Governance is the topic where fabricated allegations circulate most freely, so an integrity claim rests only on the annual report and concall transcript read at their `text_path`, NSE/BSE disclosures, the shareholding and ratio figures `get_company_fundamentals` returns, the RHP for IPOs, or a regulator order / well-known financial press — never an unknown site. An unproven allegation is not a conviction.
