"""
Alpaca Trading Bot - Time Machine (Backtester)
V3: Consolidated RSI + MACD + EMA Strategy.
"""
import os
import sys

# Fix for potential zombie directory/path issues
PROJECT_ROOT = "/Users/aryanmotgi/Downloads/AlpacaTrading-Bot-main"
if os.path.exists(PROJECT_ROOT):
    os.chdir(PROJECT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from strategy.momentum import calculate_signals
from risk.manager import calculate_position_size
import logging

# Setup basic logging for backtest
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Backtester")

class Backtester:
    def __init__(self, initial_capital=100000.0, max_pos_pct=10.0):
        self.capital = initial_capital
        self.max_pos_pct = max_pos_pct
        self.portfolio_value = initial_capital
        self.positions = [] # Current open trades
        self.trade_log = [] # History of all trades
        
    def run(self, symbol="SPY", days=180):
        logger.info(f"Starting Backtest for {symbol} (RSI + MACD + EMA) over {days} days...")
        
        # 1. Download Data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 150) # Extra for indicators
        df = yf.download(symbol, start=start_date, end=end_date, interval="1d")
        
        if df.empty:
            logger.error("No data found!")
            return
            
        # Normalize columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0].lower() for c in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]
            
        if 'adj close' in df.columns:
            df = df.drop(columns=['close'], errors='ignore')
            df = df.rename(columns={'adj close': 'close'})
            
        # 2. Replay Loop
        for i in range(125, len(df)):
            current_day = df.index[i]
            current_price = float(df['close'].iloc[i])
            historical_data = df.iloc[:i+1].copy()
            
            # --- Check Exits ---
            for pos in self.positions[:]:
                entry_price = pos['entry_price']
                stock_pnl = (current_price - entry_price) / entry_price
                if pos['type'] == 'BUY_PUT':
                    stock_pnl = -stock_pnl
                
                option_pnl = stock_pnl * 10.0 # 10x leverage proxy
                
                # Stop Loss (-15%) or Take Profit (+20%)
                if option_pnl <= -0.15 or option_pnl >= 0.20:
                    exit_val = pos['cost'] * (1 + option_pnl)
                    self.capital += exit_val
                    self.trade_log.append({
                        "symbol": symbol,
                        "entry_date": pos['date'],
                        "exit_date": current_day,
                        "type": "Exit",
                        "pnl": option_pnl * 100,
                        "result": "Win" if option_pnl > 0 else "Loss"
                    })
                    self.positions.remove(pos)

            # --- Check Entries ---
            if len(self.positions) < 1: 
                # This now calls your REAL strategy from momentum.py
                sig = calculate_signals(symbol, historical_data, historical_data)
                
                if sig['signal'] in ['BUY_CALL', 'BUY_PUT']:
                    option_premium = current_price * 0.02
                    qty = calculate_position_size(self.portfolio_value, option_premium)
                    
                    if qty > 0:
                        cost = qty * option_premium * 100
                        if self.capital >= cost:
                            self.capital -= cost
                            self.positions.append({
                                "symbol": symbol,
                                "date": current_day,
                                "entry_price": current_price,
                                "qty": qty,
                                "cost": cost,
                                "type": sig['signal']
                            })
                            logger.info(f"Entry: {current_day.date()} | {sig['signal']} @ {current_price:.2f} | Cost: ${cost:,.2f}")
            
            # Update portfolio value
            open_pos_val = 0
            for pos in self.positions:
                stock_pnl = (current_price - pos['entry_price']) / pos['entry_price']
                if pos['type'] == 'BUY_PUT': stock_pnl = -stock_pnl
                option_pnl = stock_pnl * 10.0
                open_pos_val += pos['cost'] * (1 + option_pnl)
            
            self.portfolio_value = self.capital + open_pos_val

        self.generate_report(symbol)

    def generate_report(self, symbol):
        total_trades = len(self.trade_log)
        wins = len([t for t in self.trade_log if t['result'] == "Win"])
        losses = total_trades - wins
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        total_return = ((self.portfolio_value - 100000.0) / 100000.0) * 100

        report = f"""
# 🚀 Backtest Report: {symbol}
**Date Range**: Last 6 Months
**Strategy**: CRSI + MACD + EMA (2/3 Rule)

## 📊 Performance Summary
- **Ending Portfolio Value**: ${self.portfolio_value:,.2f}
- **Total Return**: {total_return:+.2f}%
- **Win Rate**: {win_rate:.1f}% ({wins} Wins / {losses} Losses)
- **Total Trades**: {total_trades}

## 📝 Trade Log
"""
        for t in self.trade_log:
            report += f"- **{t['exit_date'].date()}**: {t['result']} | P&L: {t['pnl']:+.2f}% ({t['type']} Entry at {t['entry_date'].date()})\n"

        os.makedirs("backtests", exist_ok=True)
        report_path = f"backtests/report_{symbol}_final_crsi_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        with open(report_path, "w") as f:
            f.write(report)
        
        print(f"\nBACKTEST COMPLETE! Report saved to: {report_path}")

if __name__ == "__main__":
    tester = Backtester()
    tester.run("SPY", days=180)
