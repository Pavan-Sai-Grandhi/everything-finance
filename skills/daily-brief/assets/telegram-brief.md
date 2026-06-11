<!-- Telegram message format: plain text, no tables, no markdown links, ≤ 1500 chars.
     This file is the format spec; fill and send the text between the markers. -->

=== MESSAGE START ===
📅 {{DATE}} — Daily Brief

📈 Nifty {{NIFTY_LEVEL}} ({{NIFTY_CHG}}) | BankNifty {{BANKNIFTY_CHG}}
{{STRUCTURE_LINE}}

🔄 Sectors: ↑ {{TOP_SECTORS}} | ↓ {{BOTTOM_SECTORS}}

📋 Watchlist:
{{WATCHLIST_LINES}}
<!-- one line per ticker with a 🔴/🟡 item; if none: "— nothing material" -->

💼 Positions:
{{POSITION_LINES}}
<!-- format per line: "TICKER +4.2% | SL 3.1% away | ON-TRACK"
     SL-HIT lines start with ⛔ and lead the list -->

🎯 {{ONE_THING}}
=== MESSAGE END ===
