"""Spec-driven swing backtester for NSE daily data.

Validates any STRATEGY SPEC, not a hardcoded archetype: entry, stop, target, time-stop and
sizing all come from the spec via `finance/compute/strategy.py` — the same module the live
discover screen uses, so a new strategy is backtestable with no per-archetype code here.

Engine: Backtesting.py (MIT). Its defaults give the discipline a real-money test needs: no
lookahead (signal on bar t -> fill at t+1 open) and pessimistic intrabar exits (both stop
and target touched in one bar -> the STOP is taken). Commission is charged per side, set so
the round trip ~= 0.25% all-in (charges + slippage).

Reached through: run_backtest. `out` defaults to artifacts/backtest/<spec>/<today>/report.
"""

import json
import math
import warnings
import os
from datetime import date

from finance import paths
from finance import spine
from finance.compute import strategy
from finance.compute import ta
from finance.deps import load_yaml
from finance.sources import prices, universe

pd = ta.pd

CAVEATS = [
    "survivorship bias: current symbols only (delisted losers absent)",
    "in-sample historical test; parameter selection history is unknown; no walk-forward validation",
    "per-symbol expectancy test (each symbol sized off full capital), not a portfolio sim",
    "quantity is sized at the signal close; next-open gaps can exceed the planned risk budget",
    "each account covers its available price window; compare dates before comparing returns",
    "positions still open at the end are marked in equity, not forced into closed-trade expectancy; unpaid exit costs are excluded",
    "tests the spec's mechanical entry/exit only — not the fundamental gate "
    "or discretionary S/R reads",
]

# Per-side commission; ~0.00125/side ≈ 0.25% round trip (all-in charges + slippage).
COMMISSION_PER_SIDE = 0.00125


def load_ohlcv(symbol, years):
    """Source-owned history/cache and gaps; the source resolves the ticker."""
    return prices.history_df(symbol, period=f"{years}y", adjusted=True)


def run_symbol(df, spec, symbol, capital, risk_pct):
    """Return trades and the engine's dated, marked-to-market account equity."""
    from backtesting import Backtest
    frame = strategy.prepare_backtest_frame(df, spec)
    strat = strategy.build_bt_strategy(spec, capital, risk_pct)
    time_stop = int((spec.get("exit", {}) or {}).get("time_stop_sessions", 20) or 20)
    bt = Backtest(frame, strat, cash=capital, commission=COMMISSION_PER_SIDE,
                  exclusive_orders=True, trade_on_close=False, finalize_trades=False)
    # Finalization replays the final bar, which can execute a just-generated order
    # at that same bar's open. Keep genuine open positions and report the censoring.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Some trades remain open at the end of backtest.*", category=UserWarning)
        stats = bt.run()
    trades = []
    for _, t in stats["_trades"].iterrows():
        tag = t.get("Tag")
        initial_stop = spine.f(tag.get("initial_stop")) if isinstance(tag, dict) else None
        actual_entry = float(t["EntryPrice"])
        size = abs(float(t["Size"]))
        risk = actual_entry - initial_stop if initial_stop is not None else None
        pnl = float(t["PnL"])
        r = spine.f(pnl / (risk * size)) if risk is not None and risk > 0 and size > 0 else None
        exit_reason = _exit_reason(t, time_stop)
        trades.append({
            "symbol": symbol, "strategy": spec.get("name"),
            "entry_date": str(pd.Timestamp(t["EntryTime"]).date()),
            "entry": actual_entry, "initial_stop": initial_stop,
            "sl": float(t["SL"]) if not pd.isna(t.get("SL")) else None,
            "target": float(t["TP"]) if not pd.isna(t.get("TP")) else None,
            "qty": int(size),
            "exit_date": str(pd.Timestamp(t["ExitTime"]).date()),
            "exit": float(t["ExitPrice"]), "reason": exit_reason,
            "pnl": pnl, "r_multiple": r,
            "year": pd.Timestamp(t["ExitTime"]).year,
        })
    return {"trades": trades, "equity": stats["_equity_curve"]["Equity"].copy(),
            "open_trades": len(stats["_strategy"].trades)}


def _exit_reason(t, time_stop=None):
    """Label why a trade closed: SL (incl. a trailed stop — which can be a *win*),
    TARGET, TIME (held to the time-stop), or SIGNAL/OTHER (a discretionary
    exit_signal close). Distinguishing TIME from SIGNAL matters because
    strategy-manager's optimize step reads the exit mix as its diagnostic."""
    ex = float(t["ExitPrice"])
    # Long-only engine: an open gapping through a level fills beyond it, not at it.
    if not pd.isna(t.get("SL")) and ex <= float(t["SL"]) + 1e-6:
        return "SL"
    if not pd.isna(t.get("TP")) and ex >= float(t["TP"]) - 1e-6:
        return "TARGET"
    if (time_stop is not None and not pd.isna(t.get("ExitBar"))
            and not pd.isna(t.get("EntryBar"))
            and int(t["ExitBar"]) - int(t["EntryBar"]) >= time_stop):
        return "TIME"
    return "SIGNAL/OTHER"


def buy_and_hold(df):
    ret = float(df["Close"].iloc[-1] / df["Close"].iloc[0] - 1)
    peak = df["Close"].cummax()
    mdd = float(((df["Close"] - peak) / peak).min())
    return {"total_return_pct": round(100 * ret, 1), "max_dd_pct": round(100 * mdd, 1)}


def equity_stats(equity, capital):
    """Account statistics include initial capital and intra-trade marked equity."""
    if not math.isfinite(capital) or capital <= 0 or not len(equity) or not ta.np.isfinite(equity.to_numpy(dtype=float)).all():
        raise ValueError("need positive initial capital and finite nonempty equity")
    peak = equity.cummax().clip(lower=capital)
    stats = {
        "total_pnl": float(equity.iloc[-1] - capital),
        "return_pct": float(100 * (equity.iloc[-1] / capital - 1)),
        "max_dd_pct": float(100 * ((equity - peak) / peak).min()),
    }
    if not all(math.isfinite(value) for value in stats.values()):
        raise ValueError("account statistics are nonfinite")
    return stats


def summarize(trades, capital, equity_curves):
    """Pool trade outcomes; accounts remain independently funded per-symbol tests.

    Return uses all successfully tested accounts, including ones with no trades.
    Drawdown is the worst individual marked account drawdown, never an invented
    portfolio curve from an unordered concatenation of closed trades.
    """
    accounts = {symbol: equity_stats(curve, capital) for symbol, curve in equity_curves.items()}
    total_capital = capital * len(accounts)
    account_pnl = sum(account["total_pnl"] for account in accounts.values())
    if not math.isfinite(total_capital) or not math.isfinite(account_pnl):
        raise ValueError("combined account totals are nonfinite")
    result = {
        "trades": len(trades), "symbols_tested": len(accounts),
        "capital_per_symbol": capital, "total_initial_capital": total_capital,
        "total_account_pnl": round(account_pnl, 2),
        "return_on_capital_pct": round(100 * account_pnl / total_capital, 1) if accounts else None,
        "max_dd_on_equity_pct": round(min(a["max_dd_pct"] for a in accounts.values()), 1) if accounts else None,
        "return_basis": "equal initial capital in each independently tested symbol (including idle accounts)",
        "drawdown_basis": "worst per-symbol marked-to-market account; not portfolio drawdown",
        "max_drawdown_symbol": min(accounts, key=lambda symbol: (accounts[symbol]["max_dd_pct"], symbol)) if accounts else None,
    }
    if not trades:
        return {**result, "note": "no completed trades to assess"}
    t = pd.DataFrame(trades)
    t["r_multiple"] = t["r_multiple"].map(spine.f)
    t["year"] = pd.to_datetime(t["exit_date"]).dt.year
    wins, losses = t[t.pnl > 0], t[t.pnl <= 0]
    gross_p, gross_l = float(wins.pnl.sum()), abs(float(losses.pnl.sum()))

    def mean_r(values, places):
        # An incomplete risk denominator cannot certify the sample's expectancy.
        return round(float(values.mean()), places) if len(values) and values.notna().all() else None

    def year_label(year):
        return f"{year} (partial)" if year == date.today().year else str(year)

    result.update({
        "win_rate_pct": round(100 * len(wins) / len(t), 1),
        "avg_win_R": mean_r(wins.r_multiple, 2),
        "avg_loss_R": mean_r(losses.r_multiple, 2),
        "expectancy_R": mean_r(t.r_multiple, 3),
        "trades_missing_R": int(t.r_multiple.isna().sum()),
        "profit_factor": round(gross_p / gross_l, 2) if gross_l > 0 else None,
        "profit_factor_note": None if gross_l > 0 else "undefined: no losing P&L in the sample",
        "total_pnl": round(float(t.pnl.sum()), 0),
        "pnl_basis": "closed trades; total_account_pnl also includes marked open positions",
        "exit_breakdown": {str(k): int(v) for k, v in t.reason.value_counts().items()},
        "by_year_pnl": {year_label(k): round(float(v), 0) for k, v in t.groupby("year").pnl.sum().items()},
        "by_year_expectancy_R": {year_label(k): mean_r(group.r_multiple, 3) for k, group in t.groupby("year")},
    })
    return result


_publish = spine.publish_evidence


def run(spec, symbols, years=5, capital=500000, risk_pct=None, out=None):
    """Backtest a spec over a universe and return the shared data-spine envelope.

    `spec` is a path to a strategy YAML. `out` is a path PREFIX: content-addressed
    summary JSON, trade CSV and marked-equity CSV files (default prefix
    `artifacts/backtest/<spec>/<date>/report`). The envelope carries the performance
    summary, the buy-and-hold comparison, the caveats that qualify both, and those paths —
    the per-trade log stays on disk.
    """
    try:
        doc = load_yaml(spec)
        if not isinstance(doc, dict):
            raise ValueError("strategy must be a mapping")
        if doc.get("purpose", "trading") != "trading":
            raise ValueError("backtest requires a trading spec")
        if doc.get("direction", "long") != "long":
            raise ValueError("this backtest supports long strategies only")
        capital, risk_pct = strategy.validate_spec(doc, capital, risk_pct)
        if type(years) is not int or years <= 0:
            raise ValueError("years must be a positive integer")
        symbols, gaps = universe.resolve_symbols(symbols)
    except Exception as exc:
        return spine.envelope(False, "finance.compute.backtest", {}, [f"cannot load backtest inputs: {exc}"])
    try:
        if out is None:
            name = doc.get("name") or os.path.splitext(os.path.basename(spec))[0]
            out = os.path.join(paths.backtest_dir(name), "report")
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    except (OSError, ValueError, TypeError) as exc:
        return spine.envelope(False, "finance.compute.backtest", {}, gaps + [f"cannot prepare backtest paths: {exc}"])

    all_trades, bh, equity_curves = [], {}, {}
    open_trades = 0
    for sym in symbols:
        try:
            df, price_gaps = load_ohlcv(sym, years)
            gaps.extend(f"{sym}: {gap}" for gap in price_gaps)
            if df is None or len(df) == 0:
                raise ValueError("no usable price history")
        except Exception as exc:  # noqa: BLE001 — a data gap skips the symbol, never the run
            gaps.append(f"{sym}: {exc}")
            continue
        try:
            benchmark = buy_and_hold(df)
            tested = run_symbol(df, doc, sym, capital, risk_pct)
            # Only a successful test account contributes capital or benchmark data.
            equity_stats(tested["equity"], capital)
            all_trades.extend(tested["trades"])
            equity_curves[sym] = tested["equity"]
            bh[sym] = benchmark
            open_trades += tested["open_trades"]
        except Exception as exc:  # noqa: BLE001
            gaps.append(f"{sym}: backtest error: {exc}")

    if not all_trades:
        gaps.append("the spec produced no completed trades over this universe and window — "
                    "an untested closed-trade expectancy, not a validated one")
    all_trades.sort(key=lambda trade: (trade["exit_date"], trade["symbol"], trade["entry_date"]))
    missing_r = sum(trade["r_multiple"] is None for trade in all_trades)
    if missing_r:
        gaps.append(f"{missing_r} trades have unknown/nonpositive actual fill-to-original-stop risk; expectancy is unassessed")
    try:
        performance = summarize(all_trades, capital, equity_curves)
        performance["open_trades_at_end"] = open_trades
        json.dumps(performance, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        gaps.append(f"performance statistics unavailable: {exc}")
        performance = {"trades": len(all_trades), "note": "performance statistics unavailable"}
    result = {
        "config": {"spec": doc.get("name"), "spec_path": spec,
                   "symbols_resolved": symbols, "years": years, "capital": capital,
                   "risk_pct": risk_pct,
                   "commission_per_side": COMMISSION_PER_SIDE,
                   "engine": "Backtesting.py + finance/compute/strategy.py (spec-driven)"},
        "summary": performance,
        "buy_and_hold": bh,
        "data_gaps": gaps,
        "caveats": CAVEATS,
    }
    trades_path = equity_path = summary_path = None
    try:
        if all_trades:
            trades_path = _publish(f"{out}-trades", ".csv",
                                   lambda stream: pd.DataFrame(all_trades).to_csv(stream, index=False))
        if equity_curves:
            frame = pd.DataFrame(equity_curves).sort_index().rename_axis("date").reset_index()
            equity_path = _publish(f"{out}-equity", ".csv", lambda stream: frame.to_csv(stream, index=False))
        result.update(trades_path=trades_path, equity_path=equity_path)
        summary_path = _publish(f"{out}-summary", ".json",
                                lambda stream: json.dump(result, stream, indent=2, allow_nan=False))
    except (OSError, ValueError) as exc:
        gaps.append(f"could not persist backtest evidence: {exc}")
    return spine.envelope(
        bool(all_trades), "finance.compute.backtest",
        {"config": result["config"], "summary": result["summary"],
         "buy_and_hold": bh, "caveats": CAVEATS,
         "trades": len(all_trades), "summary_path": summary_path,
         "trades_path": trades_path, "equity_path": equity_path},
        gaps)
