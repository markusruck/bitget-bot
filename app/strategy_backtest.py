import os, time
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

SYMBOL       = os.getenv("PAIR", "BTC/USDT")
TIMEFRAME    = os.getenv("TIMEFRAME", "1h")
EMA_FAST     = int(os.getenv("EMA_FAST", "50"))
EMA_SLOW     = int(os.getenv("EMA_SLOW", "200"))
DONCHIAN_N   = int(os.getenv("DONCHIAN_N", "20"))
ATR_LEN      = int(os.getenv("ATR_LEN", "14"))
RISK_PCT     = float(os.getenv("RISK_PCT", "0.01"))
MAX_TRADES_D = int(os.getenv("MAX_TRADES_D", "1"))
COOLDOWN_H   = int(os.getenv("COOLDOWN_H", "4"))
LOSS_STREAK_MAX = int(os.getenv("LOSS_STREAK_MAX", "3"))

def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h-l).abs(), (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def fetch_ohlcv(ex, symbol, timeframe, since_ms):
    out, ms = [], since_ms
    while True:
        rows = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=ms, limit=1000)
        if not rows:
            break
        out += rows
        ms = rows[-1][0] + 1
        if len(rows) < 900:
            break
        time.sleep(ex.rateLimit / 1000)
    return out

def backtest(df, init_equity=10_000.0):
    eq = init_equity
    peak = init_equity
    max_dd = 0.0
    pos = None
    last_trade_ts = pd.Timestamp.min.tz_localize("UTC")
    trades_today = 0
    last_day = None
    loss_streak = 0
    journal = []

    start_i = max(EMA_SLOW, DONCHIAN_N, ATR_LEN) + 1
    for i in range(start_i, len(df)):
        r = df.iloc[i]
        ts = r.name
        px = float(r.close)

        if last_day != ts.date():
            trades_today = 0
            last_day = ts.date()

        if pos:
            if pos["side"] == "long" and (r.low <= pos["sl"] or r.high >= pos["tp"]):
                ex_price = pos["tp"] if r.high >= pos["tp"] else pos["sl"]
                pnlR = (ex_price - pos["entry"]) / pos["rpu"]
                eq += pnlR * pos["risk_cash"]
                loss_streak = 0 if pnlR >= 0 else loss_streak + 1
                journal.append([ts, "EXIT_LONG", ex_price, pnlR, eq])
                pos = None
            elif pos["side"] == "short" and (r.high >= pos["sl"] or r.low <= pos["tp"]):
                ex_price = pos["tp"] if r.low <= pos["tp"] else pos["sl"]
                pnlR = (pos["entry"] - ex_price) / pos["rpu"]
                eq += pnlR * pos["risk_cash"]
                loss_streak = 0 if pnlR >= 0 else loss_streak + 1
                journal.append([ts, "EXIT_SHORT", ex_price, pnlR, eq])
                pos = None

        if (ts - last_trade_ts) < pd.Timedelta(hours=COOLDOWN_H):
            pass
        elif trades_today >= MAX_TRADES_D:
            pass
        elif loss_streak >= LOSS_STREAK_MAX:
            pass
        else:
            if pos is None and pd.notna(r.atr) and r.atr > 0:
                if r.ema_fast > r.ema_slow and px > r.don_high:
                    sl = px - 1.0 * r.atr
                    tp = px + 2.0 * r.atr
                    rpu = max(px - sl, 1e-9)
                    risk_cash = eq * RISK_PCT
                    pos = {"side": "long", "entry": px, "sl": sl, "tp": tp, "rpu": rpu, "risk_cash": risk_cash}
                    last_trade_ts = ts
                    trades_today += 1
                    journal.append([ts, "ENTRY_LONG", px, 0.0, eq])
                elif r.ema_fast < r.ema_slow and px < r.don_low:
                    sl = px + 1.0 * r.atr
                    tp = px - 2.0 * r.atr
                    rpu = max(sl - px, 1e-9)
                    risk_cash = eq * RISK_PCT
                    pos = {"side": "short", "entry": px, "sl": sl, "tp": tp, "rpu": rpu, "risk_cash": risk_cash}
                    last_trade_ts = ts
                    trades_today += 1
                    journal.append([ts, "ENTRY_SHORT", px, 0.0, eq])

        peak = max(peak, eq)
        max_dd = min(max_dd, (eq - peak) / peak)

    J = pd.DataFrame(journal, columns=["time", "event", "price", "R", "equity"])
    if J.empty:
        pf, winrate, n = 0.0, 0.0, 0
    else:
        exits = J[J.event.str.startswith("EXIT")]
        wins = exits[exits.R > 0]
        losses = exits[exits.R < 0]
        pf = (wins.R.sum() / abs(losses.R.sum())) if not losses.empty else float('inf')
        winrate = len(wins) / len(exits) if not exits.empty else 0.0
        n = len(exits)

    return {
        "equity_end": eq,
        "return_pct": (eq / init_equity - 1) * 100,
        "max_drawdown_pct": max_dd * 100,
        "profit_factor": pf,
        "win_rate_pct": winrate * 100,
        "trades": n,
        "journal": J,
    }

def main():
    print("Lade Bitget-Daten…")
    ex = ccxt.bitget({'enableRateLimit': True})
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=365*2 + 30)
    rows = fetch_ohlcv(ex, SYMBOL, TIMEFRAME, since_ms=int(start.timestamp() * 1000))
    if not rows:
        print("Keine Daten erhalten.")
        return

    df = pd.DataFrame(rows, columns=["ts","open","high","low","close","vol"])
    df["ts"] = pd.to_datetime(df.ts, unit="ms", utc=True)
    df.set_index("ts", inplace=True)

    df["ema_fast"] = ema(df.close, EMA_FAST)
    df["ema_slow"] = ema(df.close, EMA_SLOW)
    df["atr"]      = atr(df, ATR_LEN)
    df["don_high"] = df.close.rolling(DONCHIAN_N).max()
    df["don_low"]  = df.close.rolling(DONCHIAN_N).min()

    res = backtest(df)
    print("\n=== Backtest (", SYMBOL, TIMEFRAME, ") ===")
    print(f"Trades: {res['trades']}")
    print(f"Win-Rate: {res['win_rate_pct']:.1f}%  PF: {res['profit_factor']:.2f}")
    print(f"MaxDD: {res['max_drawdown_pct']:.2f}%  Return: {res['return_pct']:.2f}%  Equity: {res['equity_end']:.2f}")

    if not res["journal"].empty:
        out = "/data/backtest_trades.csv"
        res["journal"].to_csv(out, index=False)
        print("Saved:", out)

if __name__ == "__main__":
    main()
