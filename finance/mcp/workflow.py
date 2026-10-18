"""finance-workflow: the plugin's own state and run machinery."""
from __future__ import annotations

from finance import paths as _paths
from finance.compute import alerts as _alerts
from finance.compute import debate as _debate
from finance.compute import strategy_library as _library
from finance.report import publication as _publication
from finance.report import render as _render
from finance.report import telegram as _telegram

from finance.mcp._server import create

SERVER = create(
    "finance-workflow",
    "The plugin's own state and run machinery: the alert inbox, prior runs, the strategy "
    "library, deep-analysis mode and debate rounds, and report bundles, decks and "
    "Telegram delivery.",
)


@SERVER.tool(
    description="The durable alert inbox — the 'watch this / do this' items skills "
                "raise and daily-brief reads. `action`: list (open alerts, severity "
                "first; `subject` filters to one id) | add | dismiss (needs "
                "`alert_id`) | snooze (needs `alert_id` and `until`) | sweep (expire "
                "the elapsed, un-snooze the due) | evaluate (fire the open price and date "
                "triggers against `prices` {SYMBOL: {close, day_change_pct, ...}} observed "
                "from decision sources, dated `as_of`; check triggers are left for a skill "
                "run). An `add` needs `subject_id`, `text` "
                "and exactly one trigger: `metric`+`op`+`level` for a price watch, "
                "`due` for a date reminder, or `check` for something needing a skill "
                "run. `dedup_key` updates a matching open alert in place instead of "
                "piling up a duplicate. Skills describe an alert in the stored shape "
                "`contracts.md` defines; it flattens onto these parameters as "
                "`subject.{type,id}` -> `subject_type`/`subject_id`, `trigger.due`, "
                "`trigger.check` and `trigger.{metric,op,level}` -> the same-named "
                "parameters, and `action.{text,suggest}` -> `text`/`suggest`."
)
def manage_alerts(action: str, alert_id: str | None = None, subject: str | None = None,
                  until: str | None = None, created_by: str = "alert-manager",
                  subject_type: str = "stock", subject_id: str | None = None,
                  kind: str = "custom", metric: str | None = None,
                  op: str | None = None, level: float | None = None,
                  due: str | None = None, check: str | None = None,
                  text: str | None = None, suggest: str | None = None,
                  severity: str = "watch", expires_at: str | None = None,
                  dedup_key: str | None = None, prices: dict | None = None,
                  as_of: str | None = None) -> dict:
    return _alerts.manage(action, alert_id=alert_id, subject=subject, until=until,
                          created_by=created_by, subject_type=subject_type,
                          subject_id=subject_id, kind=kind, metric=metric, op=op,
                          level=level, due=due, check=check, text=text,
                          suggest=suggest, severity=severity, expires_at=expires_at,
                          dedup_key=dedup_key, prices=prices, as_of=as_of)


@SERVER.tool(
    description="Path to the previous dated run of a per-entity skill for one subject, "
                "so a re-run builds on its own history instead of starting cold. "
                "`skill` is one of deep-analysis | fundamentals | dcf | management | "
                "filings (stocks, `subject` = NSE symbol) or mf-analysis (funds, "
                "`subject` = scheme name). `before` (YYYY-MM-DD) defaults to today and is "
                "exclusive. No earlier run returns ok:true with a null `path` — a first "
                "run is the normal case, not a gap."
)
def get_prior_run(skill: str, subject: str, before: str | None = None) -> dict:
    return _paths.prior_run(skill, subject, before=before)


@SERVER.tool(
    description="Pick the active strategy that fits today's market. Keeps status:active "
                "specs (of `purpose` trading | investment when given) whose "
                "regime_required today's market-context artifact satisfies, ranked by "
                "verified live expectancy, else backtest expectancy (trading), or recency "
                "(investment). `outcome` is selected | none_fit | no_active. Needs "
                "get_market_context to have run today."
)
def select_strategy(purpose: str | None = None, out: str | None = None) -> dict:
    return _library.select_report(want=purpose, out=out)


@SERVER.tool(
    description="Aggregate execution-verified closed trades per strategy: win rate, "
                "expectancy in R, R-weighted profit factor and exit reasons, with a "
                "KEEP / OPTIMIZE / DEACTIVATE verdict, or REVIEW when any close lacks "
                "broker execution evidence or does not reconcile. `update_spec` writes "
                "live_performance into each spec and deactivates on a complete negative "
                "sample of at least ten closes."
)
def review_strategy_performance(strategy: str | None = None, update_spec: bool = False,
                                out: str | None = None) -> dict:
    return _library.performance_report(strategy, update_spec, out=out)


@SERVER.tool(
    description="Resolve the deep-analysis run mode: quick | standard | deep | "
                "fundamentals. An explicit flag in `args` wins (--fundamentals over --deep "
                "over --quick); else a live holding or an open trade record for `symbol` "
                "escalates to deep; else standard. `holding` is your broker check: yes | "
                "no | unknown — unknown resolves like no but returns a gap."
)
def resolve_analysis_mode(args: str, symbol: str | None = None,
                          holding: str = "unknown") -> dict:
    return _debate.mode_report(args, symbol=symbol, holding=holding)


@SERVER.tool(
    description="Decide whether the bull/bear debate runs another round, from both sides' "
                "debate-block digests {axis, claim, conceded, new_evidence} for round "
                "`round`. Different axes -> a cross-examination round; same axis with "
                "distinct claims -> a rebuttal round; a concession, a restated claim, no "
                "new evidence after round 1, or round 3 ends it. Put the returned "
                "`directive` in both next-round prompts. ok:false means a digest broke "
                "its contract."
)
def decide_debate_round(bull: dict, bear: dict, round: int = 1) -> dict:
    return _debate.round_report(bull, bear, round_no=round)


@SERVER.tool(
    description="Create the staging bundle for one deep-analysis report (standard, deep "
                "or fundamentals): returns run_dir, report_json, report_html and "
                "agents_dir. `session` is the SessionStart session id. `telegram: true` "
                "only when the user asked for delivery."
)
def prepare_report(session: str, ticker: str, date: str, mode: str,
                   telegram: bool = False) -> dict:
    return _publication.prepare_report(session, ticker, date, mode, telegram)


@SERVER.tool(
    description="Render a report.json projection into one self-contained HTML deck with a "
                "bundled template: deep-analysis | mf-analysis | sector-analysis | "
                "wealth-report | daily-brief. The projection's shape is the worked "
                "example at finance/report/fixtures/<template>.sample.json. `out` "
                "defaults to report.html beside the JSON."
)
def render_report(report_json: str, template: str, out: str | None = None) -> dict:
    return _render.render_report(report_json, template, out)


@SERVER.tool(
    description="Archive a ready report bundle (its run_dir holds an empty `ready` file) "
                "to stocks/<TICKER>/<date>/runs/<run-id>/, then send the deck to Telegram "
                "when prepare_report recorded the user's request. A failed or uncertain "
                "send is a gap and is never retried."
)
def publish_report(session: str, run_id: str) -> dict:
    return _publication.publish_report(session, run_id)


@SERVER.tool(
    description="Send one text message to the user's Telegram chat from a local text "
                "file. Only when the user asked for it. The message is plain text up to "
                "4096 characters; a failed or uncertain send is a gap and is never retried."
)
def send_telegram(text_file: str) -> dict:
    return _telegram.send_text_file(text_file)


def main():
    SERVER.run("stdio")


if __name__ == "__main__":
    main()
