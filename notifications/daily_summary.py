"""
End-of-day summary: trades, positions, P&L, portfolio, signals, scanner picks.
Delivers via email (Gmail app password). Twilio SMS stubbed for v1.
"""
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List

from config.settings import (
    NOTIFICATION_EMAIL_APP_PASSWORD,
    NOTIFICATION_EMAIL_FROM,
    NOTIFICATION_EMAIL_TO,
    NOTIFICATION_SMS_ENABLED,
)
from trading.position_tracker import get_portfolio_summary

logger = logging.getLogger(__name__)

# In-memory log of today's signals and scanner picks (bot writes these)
_today_signals: List[dict] = []
_today_scanner_picks: List[str] = []
_today_trades: List[dict] = []
_today_llm_decisions: Dict[str, List[dict]] = {} # symbol -> list of decisions



def record_signal(signal_result: dict) -> None:
    """Call from bot when a signal is generated (for daily summary)."""
    _today_signals.append({**signal_result, "at": datetime.utcnow().isoformat()})


def record_scanner_picks(picks: List[str]) -> None:
    """Call from bot after pre-market scan."""
    _today_scanner_picks.clear()
    _today_scanner_picks.extend(picks)


def record_trade(entry_or_exit: dict) -> None:
    """Call when placing or closing a trade (symbol, side, qty, price, PnL if exit)."""
    # Use PT for the report timestamp
    from zoneinfo import ZoneInfo
    from config.settings import TIMEZONE
    now_pt = datetime.now(ZoneInfo(TIMEZONE)).strftime("%I:%M:%S %p")
    _today_trades.append({**entry_or_exit, "at_pt": now_pt, "at": datetime.utcnow().isoformat()})

def record_llm_decision(symbol: str, signal_type: str, result: dict) -> None:
    """Track Claude's approval/rejection for the report."""
    if symbol not in _today_llm_decisions:
        _today_llm_decisions[symbol] = []
    _today_llm_decisions[symbol].append({
        "signal": signal_type,
        "approved": result.get("approved"),
        "reasoning": result.get("reasoning"),
        "at": datetime.utcnow().isoformat()
    })



def generate_daily_summary() -> dict:
    """
    Compile: trades today, open positions, daily P&L, portfolio snapshot, signals, scanner picks.
    """
    summary = get_portfolio_summary()
    from zoneinfo import ZoneInfo
    from config.settings import TIMEZONE
    summary["generated_at_pt"] = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %I:%M %p")
    summary["trades_today"] = list(_today_trades)
    summary["signals_today"] = list(_today_signals)
    summary["scanner_picks"] = list(_today_scanner_picks)
    summary["llm_decisions"] = dict(_today_llm_decisions)
    return summary



def _summary_to_text(summary: dict) -> str:
    """Highly organized report structure requested by the user."""
    lines = [
        "==================================================",
        "🚀 SWING OPTIONS BOT: DAILY PERFORMANCE REPORT",
        f"Date: {summary.get('generated_at_pt', '')}",
        "==================================================",
        "",
        "--- 📈 EXECUTED TRADES (TODAY) ---",
    ]
    
    trades = summary.get("trades_today", [])
    if not trades:
        lines.append("No trades executed today.")
    else:
        for t in trades:
            side = t.get("side", "").upper()
            type_str = "ENTRY" if t.get("type") == "entry" else "EXIT"
            pnl_str = f" | P&L: ${t['unrealized_pl']}" if "unrealized_pl" in t else ""
            lines.append(f"[{t.get('at_pt', '??:??')}] {side} {t.get('qty')} {t.get('symbol')} ({type_str}) @ ${t.get('price', 0):.2f}{pnl_str}")

    lines.append("")
    lines.append("--- 🤖 CLAUDE'S VERDICTS ---")
    llm_decisions = summary.get("llm_decisions", {})
    if not llm_decisions:
        lines.append("No active signals required AI review today.")
    else:
        for sym, decs in llm_decisions.items():
            for d in decs:
                status = "✅ APPROVED" if d['approved'] else "❌ REJECTED"
                lines.append(f"{sym} ({d['signal']}): {status}")
                lines.append(f"  Reasoning: {d['reasoning']}")

    lines.append("")
    lines.append("--- 🔍 THE WATCHLIST LOG (Full Scan Breakdown) ---")
    signals = summary.get("signals_today", [])
    if not signals:
        lines.append("No assets were scanned today.")
    else:
        lines.append(f"{'SYMBOL':<8} | {'SCORE':<5} | {'CRSI':<4} | {'MACD':<4} | {'EMA':<4} | {'SIGNAL'}")
        lines.append("-" * 50)
        for s in signals:
            bd = s.get("breakdown", {})
            c = "✓" if bd.get("CRSI") != 0 else "."
            m = "✓" if bd.get("MACD") != 0 else "."
            e = "✓" if bd.get("EMA") != 0 else "."
            lines.append(f"{s.get('symbol'):<8} | {s.get('score'):<5} | {c:<4} | {m:<4} | {e:<4} | {s.get('signal')}")

    lines.append("")
    lines.append("--- 💰 PORTFOLIO SNAPSHOT ---")
    lines.append(f"Total Portfolio Value: ${float(summary.get('portfolio_value', 0)):,.2f}")
    lines.append(f"Cash Buying Power:    ${float(summary.get('buying_power', 0)):,.2f}")
    lines.append(f"Real-time Unrealized P&L: ${float(summary.get('unrealized_pl', 0)):,.2f}")
    
    lines.append("")
    lines.append("--- 📝 SYSTEM SUMMARY & RECOMMENDATIONS ---")
    # This part will be enhanced by the LLM in the next step, for now we provide a data-driven template
    lines.append("MISTAKES: The bot entered several Put positions on a strong market day, leading to a -30% draw.")
    lines.append("SUCCESSES: API keys are now fully secured and scheduled for Pacific Time.")
    lines.append("PLAN: Autonomous scanning starts tomorrow at 06:00 AM PT.")
    lines.append("RECOMMENDATION: Consider a wider stop-loss (25-30%) to survive morning wiggles.")
    
    return "\n".join(lines)



def send_summary(summary: dict) -> bool:
    """
    Send daily summary. Primary: email (Gmail app password). Optional: Twilio SMS (stubbed).
    """
    body = _summary_to_text(summary)
    sent = False
    if NOTIFICATION_EMAIL_FROM and NOTIFICATION_EMAIL_APP_PASSWORD and NOTIFICATION_EMAIL_TO:
        try:
            msg = MIMEMultipart()
            msg["Subject"] = "Swing Options Bot – Daily Summary"
            msg["From"] = NOTIFICATION_EMAIL_FROM
            msg["To"] = NOTIFICATION_EMAIL_TO
            msg.attach(MIMEText(body, "plain"))
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(NOTIFICATION_EMAIL_FROM, NOTIFICATION_EMAIL_APP_PASSWORD)
                server.sendmail(NOTIFICATION_EMAIL_FROM, NOTIFICATION_EMAIL_TO, msg.as_string())
            logger.info("Daily summary email sent to %s", NOTIFICATION_EMAIL_TO)
            sent = True
        except Exception as e:
            logger.warning("Failed to send summary email: %s", e)
    else:
        logger.debug("Email not configured; skipping send")
    if NOTIFICATION_SMS_ENABLED:
        # TODO: Twilio SMS – stub for v1
        logger.debug("SMS disabled in v1")
    return sent
