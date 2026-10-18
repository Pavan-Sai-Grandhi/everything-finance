# Method sources

Every rule in a method file cites one of these ids. A rule may cite several sources that agree.
The order of this table is the priority used when a topic file names no lead source; how
disagreements are settled is in `CLAUDE.md` → *Methods and sources*.

Citation format: `[id]`, or `[id:locator]` for a chapter, part or timestamp:
`[varsity-ta:19]`, `[damodaran:narrative-and-numbers]`, `[<channel>:<video-id>@mm:ss]`.

| id | Source | Kind | Covers |
|---|---|---|---|
| `law` | Companies Act 2013, SEBI LODR, SEBI and RBI circulars, IRDAI regulations | statute and regulator | what a rule legally is: remuneration ceilings, disclosures, insurance terms |
| `varsity-ta` | Zerodha Varsity, [Technical Analysis](https://zerodha.com/varsity/module/technical-analysis/), 22 chapters | broker curriculum | candlesticks, support and resistance, volume, Dow theory, indicators, the trade checklist |
| `varsity-ts` | Zerodha Varsity, [Trading Systems](https://zerodha.com/varsity/module/trading-systems/), 16 chapters | broker curriculum | system design, expectancy, sizing, backtesting |
| `varsity-fa` | Zerodha Varsity, [Fundamental Analysis](https://zerodha.com/varsity/module/fundamental-analysis/) | broker curriculum | ratio analysis, the equity-research checklist |
| `varsity-sa` | Zerodha Varsity, [Sector Analysis](https://zerodha.com/varsity/module/sector-analysis/) | broker curriculum | cement, insurance, IT, automobiles, banking, steel, hotels, retail, real estate |
| `varsity-pf` | Zerodha Varsity, [Personal Finance](https://zerodha.com/varsity/module/personalfinance/), 33 chapters | broker curriculum | fund mechanics, performance measurement (ch. 18–23), fund analysis (ch. 24–26), financial planning |
| `varsity-ins` | Zerodha Varsity, [Insurance](https://zerodha.com/varsity/module/insurance/), 9 chapters by Ditto | broker curriculum | protection over investment, disclosure, riders |
| `damodaran` | Aswath Damodaran, *The Little Book of Valuation* and *Narrative and Numbers*; his India valuations (Zomato, Adani) | practitioner | story-driven DCF, country risk, terminal value, relative valuation |
| `moneypurse-mgmt` | Money Purse, "Select stocks like an expert", Parts 2A/2B | practitioner | management integrity and skill; builds on Vijay Malik's checklists and Philip Fisher |
| `soic` | SOIC, "Unlock Hidden Investment Opportunities: Special Situations Explained" (soic.in) | practitioner | the special-situation event taxonomy |
| `quantinsti` | QuantInsti, [backtesting guide](https://www.quantinsti.com/articles/backtesting-trading/) | practitioner | backtest biases |
| `marketcalls` | Marketcalls, [look-ahead bias](https://www.marketcalls.in/python/understanding-look-ahead-bias-and-how-to-avoid-it-in-trading-strategies.html) | practitioner | look-ahead bias |
| `fortraders` | ForTraders, [bias guide](https://www.fortraders.com/blog/how-to-avoid-bias-in-backtesting) | practitioner | backtest biases |
| `plugin` | this plugin's own bars and conventions | house rule | thresholds and procedures no source above sets |

A user-supplied document (a strategy article, the user's budget workbook, a policy wording) is
cited by what it is, inside the run that uses it. It is not a registry source.

## Adding a source

Give it an id and a row here, with its kind, what it covers, and its link or episode list. Distill
it first; YouTube channels go through `../yt-distill`, whose notes carry `[mm:ss]` timestamps for
the locator. Then merge each rule into the topic it belongs to, as `CLAUDE.md` describes.
