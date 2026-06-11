#!/usr/bin/env python3
"""Market-technical regime reader for strategy-manager (everything-finance plugin).

Computes from yfinance — no bot-wall, no auth:
  - Nifty 50 trend: price vs 50/200-EMA + 50-EMA slope
  - India VIX: level + 1y percentile (volatility regime)
  - Breadth proxy: % of NSE sectoral indices above their own 50-EMA
  - A risk posture (risk-on | neutral | risk-off) summarizing the above

This is the system framework's RISK GATE only — it reports the regime so the
skill can check it against the conditions the user's *reference article* claims
its strategy needs. It does NOT pick or recommend a strategy/archetype; the
trade logic always comes from the article. Macro (repo/CPI/USD-INR/FII-DII) is
layered on by the skill; this script is the objective, repeatable floor.

Usage: python3 regime.py --out artifacts/2026-06-11/regime.json
"""
import argparse, json, sys, subprocess
from datetime import date

try:
    import pandas as pd
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet",
                           "--break-system-packages", "pandas", "yfinance"])
    import pandas as pd

NIFTY = "^NSEI"
VIX = "^INDIAVIX"
SECTORS = {  # verified yfinance NSE sectoral tickers (see sector-pulse reference)
    "Bank": "^NSEBANK", "FinServ": "NIFTY_FIN_SERVICE.NS", "IT": "^CNXIT",
    "Pharma": "^CNXPHARMA", "Auto": "^CNXAUTO", "FMCG": "^CNXFMCG",
    "Metal": "^CNXMETAL", "Realty": "^CNXREALTY", "Energy": "^CNXENERGY",
    "PSUBank": "^CNXPSUBANK",
}


def dl(ticker, period="1y"):
    import yfinance as yf
    df = yf.download(ticker, period=period, interval="1d",
                     auto_adjust=True, progress=False)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df["Close"].dropna()


def ema(s, span):
    return s.ewm(span=span, adjust=False).mean()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=f"artifacts/{date.today()}/regime.json")
    args = p.parse_args()
    gaps = []

    # --- Nifty trend ---
    nifty = dl(NIFTY, "2y")
    trend = {}
    if nifty is None or len(nifty) < 200:
        gaps.append("Nifty data unavailable — trend gate could not be computed")
        market_trend = "unknown"
    else:
        e50, e200 = ema(nifty, 50), ema(nifty, 200)
        px = float(nifty.iloc[-1])
        slope50 = float(e50.iloc[-1] - e50.iloc[-20])  # 50-EMA rising?
        above50, above200 = px > float(e50.iloc[-1]), px > float(e200.iloc[-1])
        if above50 and above200 and slope50 > 0:
            market_trend = "up"
        elif (not above50) and (not above200) and slope50 < 0:
            market_trend = "down"
        else:
            market_trend = "range"
        trend = {"nifty": round(px, 1), "ema50": round(float(e50.iloc[-1]), 1),
                 "ema200": round(float(e200.iloc[-1]), 1),
                 "above_ema50": above50, "above_ema200": above200,
                 "ema50_rising": slope50 > 0}

    # --- India VIX volatility regime ---
    vix = dl(VIX, "1y")
    if vix is None or len(vix) < 30:
        gaps.append("India VIX unavailable — volatility regime defaulted to 'normal'")
        vix_level, vix_pct, vol_regime = None, None, "normal"
    else:
        vix_level = float(vix.iloc[-1])
        vix_pct = round(100 * (vix < vix_level).mean(), 0)
        vol_regime = "low" if vix_level < 13 else ("high" if vix_level > 20 else "normal")

    # --- Breadth proxy: sectors above their 50-EMA ---
    above, total = 0, 0
    sector_detail = {}
    for name, tk in SECTORS.items():
        s = dl(tk, "6mo")
        if s is None or len(s) < 50:
            sector_detail[name] = None
            continue
        ok = float(s.iloc[-1]) > float(ema(s, 50).iloc[-1])
        sector_detail[name] = ok
        above += int(ok); total += 1
    breadth_pct = round(100 * above / total, 0) if total else None
    if breadth_pct is None:
        gaps.append("Sectoral breadth unavailable")
        breadth = "unknown"
    else:
        breadth = "strong" if breadth_pct > 60 else ("weak" if breadth_pct < 40 else "mixed")

    # --- Risk posture (a summary of the gate, NOT a strategy recommendation) ---
    # The skill checks this against the conditions the user's reference article claims.
    if market_trend == "up" and vol_regime != "high" and breadth in ("strong", "mixed"):
        posture, why = "risk-on", "Uptrend + acceptable vol + participation: directional/long systems have a tailwind."
    elif vol_regime == "high" or market_trend == "down" or breadth == "weak":
        posture, why = "risk-off", "Down/high-vol/weak-breadth: size down or stand aside; trend-following will whipsaw."
    else:
        posture, why = "neutral", "No clear trend or mixed participation: confirmation-heavy, modest size."

    result = {
        "as_of": str(date.today()),
        "market_trend": market_trend,            # up | range | down
        "trend_detail": trend,
        "volatility": {"vix": round(vix_level, 2) if vix_level else None,
                       "vix_1y_percentile": vix_pct, "regime": vol_regime},
        "breadth": {"pct_sectors_above_ema50": breadth_pct, "regime": breadth,
                    "detail": sector_detail},
        "risk_posture": posture,                 # risk-on | neutral | risk-off
        "rationale": why,
        "data_gaps": gaps,
        "note": "Regime gate only — reports the tape so the skill can test it against the "
                "conditions the source article claims. Does not pick a strategy. Layer macro "
                "(repo/CPI/USD-INR/FII-DII) on top before sizing.",
    }
    import os
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))
    print(f"\nwrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
