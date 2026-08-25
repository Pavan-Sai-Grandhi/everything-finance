# {{TICKER}} — Deep Analysis ({{DATE}})

> **{{CALL}}** · conviction {{CONVICTION}} · CMP ₹{{CMP}}{{COMPANY_NAME_SUFFIX}} · depth: {{MODE}}
> {{ONE_LINE_THESIS}}

<!-- QUICK_BANNER: include this block ONLY in `quick` mode; delete it entirely in the others. -->
> ⚡ **Quick read — not full diligence.** Skipped: the annual report & concall, and the management, news, and sector lenses. Re-run `/deep-analysis {{TICKER}}` (standard) or `--deep` for the full debate. ({{MODE_REASON}})

<!-- FUNDAMENTALS_BANNER: include this block ONLY in `fundamentals` mode; delete it entirely in the others. -->
> 📊 **Fundamentals only — no position call.** Ran: financials, management, valuation. Skipped: the technical, news and sector lenses, the debate, and the portfolio-manager's verdict. Re-run `/deep-analysis {{TICKER}}` for the full debate. ({{MODE_REASON}})

## Telegram Brief
{{CALL}} {{TICKER}} @ ₹{{CMP}} (conviction: {{CONVICTION}})
🐂 {{TOP_BULL_POINT}}
🐻 {{TOP_BEAR_POINT}}
🧭 Sector: {{SECTOR_STANCE_ONELINE}}
Key level: {{KEY_LEVEL}}
Invalidation: {{INVALIDATION}}
Review: {{REVIEW_TRIGGER}}

<!-- In `fundamentals` mode: the brief instead carries the fundamentals verdict
     (investment-grade / watch / avoid), the integrity gate, the intrinsic range with its DCF
     confidence, and the strongest red flag — same ≤ 10 lines, same section heading. {{CALL}}
     is that verdict and there is no conviction; section 1's table keeps only Verdict and
     Review trigger; sections 4 and 5 are deleted whole; the At-a-Glance table marks Sector,
     Technical and News "not run (fundamentals)". -->

<!-- The Stop hook extracts exactly the section above and sends it to Telegram.
     Keep it ≤ 10 lines, no markdown tables, no links.
     This whole report is SYNTHESIZED by the report-writer from the leg work papers in
     ./agents/ — write prose, don't paste raw leg reports. Fill every {{PLACEHOLDER}}. -->

---

<!-- WHAT_CHANGED: include this whole block ONLY when get_prior_run found an earlier run;
     delete it entirely on a first-ever analysis. -->
## What changed since {{PRIOR_DATE}}
Prior run: `{{PRIOR_PATH}}`
- Verdict: {{PRIOR_CALL}} → {{CALL}}
- DCF fair value: {{PRIOR_FAIR_VALUE}} → {{FAIR_VALUE}}
- Thesis intact? {{THESIS_DELTA}}
- New risk: {{NEW_RISK_SINCE_PRIOR}}

---

## 1 · The Call
{{CALL_NARRATIVE}}
<!-- Two or three short paragraphs, one idea each: what decided the verdict; which lenses agreed
     (confluence) and which conflicted; the single biggest risk to being wrong. Plain English,
     no agent jargon. -->

| | |
|---|---|
| **Verdict** | {{CALL}} · conviction {{CONVICTION}} |
| **What it's worth** | {{VALUE_STANCE}} · call carried by {{ACTION_DRIVER}} |
| **Your position** | {{POSITION_LINE}} |
| **Entry / Stop / Target** | {{ENTRY_SL_TARGET}} · RRR {{RRR}} |
| **Allocation cap** | {{ALLOC_CAP}} |
| **Invalidation** | {{INVALIDATION}} |
| **Review trigger** | {{REVIEW_TRIGGER}} |
| **Evidence** | {{EVIDENCE_COUNTS}} · weakest load-bearing input: {{WEAKEST_INPUT}} |
<!-- VALUE_STANCE is what the business is worth (the valuation leg's, unchanged); CALL is what
     to do about it. They come apart routinely — say so when they do.
     POSITION_LINE: the holding and the hold/trim/exit call when position.held is yes;
     "not held" or "broker check unavailable" otherwise. Never leave it blank.
     EVIDENCE_COUNTS and WEAKEST_INPUT come from the verdict-block — they say how much the
     call rests on sourced figures versus derived and estimated ones. -->

## 2 · At a Glance — the lenses
| Lens | Stance | One-line read |
|---|---|---|
| 🧭 Sector | {{SECTOR_STANCE}} | {{SECTOR_ONELINE}} |
| 📈 Technical | {{TECH_STANCE}} | {{TECH_ONELINE}} |
| 📊 Financials | {{FUND_STANCE}} | {{FUND_ONELINE}} |
| 🛡️ Management | {{MGMT_STANCE}} | {{MGMT_ONELINE}} |
| ⚖️ Valuation | {{VAL_STANCE}} | {{VAL_ONELINE}} |
| 📰 News & sentiment | {{NEWS_STANCE}} | {{NEWS_ONELINE}} |
<!-- standard/deep show all six. In a mode that ran fewer, mark the rows that did not run
     "not run (<mode>)" rather than dropping them, so the gap is visible.
     Valuation one-line carries the combined stance + DCF confidence (low/med/high).
     Management stance is the integrity gate (PASS/FLAG/FAIL) + skill grade; a FAIL here forces the verdict to Avoid. -->

## 3 · Company Overview
{{COMPANY_OVERVIEW}}
<!-- Lift from the financials leg's "Company overview": what it does, segments & revenue mix,
     geography, flagship products, the moat — so a reader meeting the company here is oriented. -->

## 4 · The Debate — {{DEBATE_ROUNDS}}
<!-- rounds_run + the escalation helper's stop reason, e.g. "3 rounds (hit the deep cap)",
     "2 rounds (the bull conceded)", "2 rounds (neither side brought new evidence)",
     "1 round (a side gave no evidence-tied claim)", or "single contest (quick)".
     Where the sides argued different axes and never engaged, say so here — neither
     position survived scrutiny, and that is a caveat on the verdict, not a detail. -->
**🐂 Bull thesis.** {{BULL_SYNTHESIS}}
<!-- Distill the bull's strongest *surviving* arguments across all rounds (or the contest's bull side) + conviction into prose. -->

**🐻 Bear thesis.** {{BEAR_SYNTHESIS}}
<!-- Same for the bear — what still stood after rebuttal (or the contest's bear side), and anything it conceded.
     In `quick`, if the contest lean was "genuinely split", say so here and suggest re-running standard/deep. -->

**⚖️ What decided it.** {{DECISIVE_POINTS}}
<!-- Which arguments the portfolio-manager kept, which it discarded, where the debate landed, and the dissent worth keeping. -->

## 5 · Sector Context
{{SECTOR_CONTEXT}}
<!-- From the sector leg: where the sector sits in rotation, the tailwind & headwind that
     matter, and specifically where {{TICKER}} sits within its sector (leader/laggard, RS vs sector). -->

## 6 · Evidence by Lens
**Technical.** {{TECH_EVIDENCE}}
<!-- Trend stage, key S/R levels with the decision level, volume signature, indicator confirmation. -->

**Financials.** {{FUND_EVIDENCE}}
<!-- Checklist scorecard highlights, annual-report findings, concall takeaways, relative valuation vs peers/own band. -->

**Management.** {{MGMT_EVIDENCE}}
<!-- Integrity gate (PASS/FLAG/FAIL with the finding) + skill grade. A FAIL here is the headline — verdict Avoid regardless. -->

**Valuation.** {{VAL_EVIDENCE}}
<!-- DCF intrinsic range & margin of safety, the DCF-confidence grade (and why), reverse-DCF read, relative cross-check. -->

**News & sentiment.** {{NEWS_EVIDENCE}}
<!-- Sentiment score, the material dated facts vs narrative, recurring theme, event risk ahead. -->

## 7 · Data Gaps & Caveats
{{DATA_GAPS}}
<!-- Union of every leg's gaps, the orchestrator's own (a failed broker check, a leg that did
     not return, a phase-0 call that was skipped), and the lenses this mode did not run.
     Missing evidence is uncertainty, not neutral. Do not trim this section for length. -->

---
<details>
<summary>Work papers — full leg reports</summary>

The raw, unedited report from each leg is archived beside this file, in the folder named after
it — the legs that ran, plus `contest` in quick or `bull-r1…N`, `bear-r1…N` in standard/deep, and
verdict. The valuation and management legs write to this same run-day folder as `dcf.md`
(+ `dcf.json`) and `management.md`. This report is the synthesis of those; consult them for the
full evidence trail.
</details>

*Generated by the everything-finance deep-analysis debate ({{AGENT_COUNT}} agents). Not investment advice — personal research tool.*
