# Special situations

**Consumers:** discover (`stocks --special-situations`). **Sources, in priority order:** `soic`,
`plugin`.

A special situation is an **event**, not a ratio, so it is found in filings and corporate actions,
never in a fundamental screen. The eight event types and the "buy the value creation, not the
event" discipline are SOIC's [soic]; the tool mapping is the plugin's.

## The event taxonomy (what to scan for)

| Event | Why it can create value | The signal that matters |
|---|---|---|
| **Demerger / spin-off** | Splits a conglomerate so each division's true value shows; often cleaner governance and debt reduction | Focus on core competency, transparency of the parts, post-split debt path — the sum-of-parts vs the pre-split price |
| **Buyback** | Management says the stock is undervalued (a claim, not evidence); EPS-accretive only when the cash was earning less after tax than the earnings yield at the buyback price | Backed by real cash flow (not debt); tender vs open-market; buyback price vs market |
| **Merger / acquisition** | Scale, market share, synergy | Who gets the synergy — acquirer or target; price paid; integration risk |
| **Delisting** | Promoter buying out minorities, usually at a premium | Floor price vs market; promoter intent and cash; reverse-book-building dynamics |
| **Open offer** | Triggered acquirer bid to minorities | Offer price vs market; acceptance ratio |
| **Rights issue** | Discounted capital to existing holders | Use of proceeds (growth vs plugging a hole); discount to market |
| **Bonus / stock split** | Cosmetic — more shares, same value | Low signal on its own; read only as a liquidity/confidence gesture, never a thesis |
| **Preferential issue** | Selective issuance to specific investors | Who is buying in and at what price (marquee investor = signal; promoter dilution = flag) |

**Discipline (SOIC):** the corporate action is the *trigger to look*, not the reason to buy. The
buy case is the underlying value creation — a demerger of two mediocre businesses is still two
mediocre businesses. Bonus/split carry no value on their own.

## Scope

SOIC's *proxy investing* (theme → value-chain → supplier concentration)
is a related qualitative method with no event trigger and no ratio — it is research, not a scan, and
is deliberately out of this scanner's scope.
