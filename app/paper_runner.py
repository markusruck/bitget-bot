import os, time, json, requests
import ccxt
import pandas as pd
from datetime import datetime, timezone
# --- DEBUG + Telegram Startup-Ping ------------------------------------------
import os, sys, time

print("[INIT] TELEGRAM ENV present:",
      bool(os.getenv("TELEGRAM_BOT_TOKEN")),
      bool(os.getenv("TELEGRAM_CHAT_ID")))

print("[INIT] CWD:", os.getcwd())
try:
    print("[INIT] LS:", os.listdir("."))
except Exception as _e:
    print("[INIT] LS failed:", _e)

def _startup_ping():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat  = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[WARN] Missing TELEGRAM env, skipping Telegram ping")
        return
    try:
        import urllib.request, urllib.parse
        data = urllib.parse.urlencode({"chat_id": chat, "text": "✅ Paper-Runner gestartet."}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        with urllib.request.urlopen(req, timeout=10) as r:
            print("[OK] Telegram ping sent, status:", r.status)
    except Exception as e:
        print("[ERR] Telegram ping failed:", e)
# ---------------------------------------------------------------------------

PAIR  = os.getenv("PAIR", "BTC/USDT")
TF    = os.getenv("TIMEFRAME", "1h")
EMA_FAST = int(os.getenv("EMA_FAST", "50"))
EMA_SLOW = int(os.getenv("EMA_SLOW", "200"))
DON      = int(os.getenv("DONCHIAN_N", "20"))
ATR_LEN  = int(os.getenv("ATR_LEN", "14"))
MAX_TRADES_D     = int(os.getenv("MAX_TRADES_D", "1"))
COOLDOWN_H       = int(os.getenv("COOLDOWN_H", "4"))
LOSS_STREAK_MAX  = int(os.getenv("LOSS_STREAK_MAX", "3"))
POLL_SECONDS     = int(os.getenv("POLL_SECONDS", "300"))
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
STATE = "/data/state.json"
LOG   = "/data/paper_trades.csv"

def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h-l).abs(), (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def send(msg: str):
    if BOT_TOKEN and CHAT_ID:
        try:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": CHAT_ID, "text": msg}, timeout=8
            )
        except Exception:
            pass

def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return {"last_trade_iso": None, "trades_today": 0, "last_day": None, "loss_streak": 0, "position": None}

def save_state(s): open(STATE, "w").write(json.dumps(s, indent=2))

def log(row):
    new = not os.path.exists(LOG)
    with open(LOG, "a") as f:
        if new:
            f.write("time,event,price,side,sl,tp,R\n")
        f.write(",".join(str(x) for x in row) + "\n")

def fetch_df(ex):
    rows = ex.fetch_ohlcv(PAIR, timeframe=TF, limit=400)
    df = pd.DataFrame(rows, columns=["ts","open","high","low","close","vol"])
    df["ts"] = pd.to_datetime(df.ts, unit="ms", utc=True)
    df.set_index("ts", inplace=True)
    df["ema_fast"] = ema(df.close, EMA_FAST)
    df["ema_slow"] = ema(df.close, EMA_SLOW)
    df["atr"]      = atr(df, ATR_LEN)
    df["don_high"] = df.close.rolling(DON).max()
    df["don_low"]  = df.close.rolling(DON).min()
    return df

def main():
    ex = ccxt.bitget({'enableRateLimit': True})
    state = load_state()
    send("Paper-Runner gestartet (kein Echtgeld).")
    while True:
        try:
            df = fetch_df(ex)
            r = df.iloc[-1]
            ts = r.name
            px = float(r.close)
            atrv = float(r.atr) if pd.notna(r.atr) else 0.0

            day = str(ts.date())
            if state["last_day"] != day:
                state["last_day"] = day
                state["trades_today"] = 0

            if state["position"]:
                p = state["position"]
                if p["side"] == "long":
                    if r.low <= p["sl"] or r.high >= p["tp"]:
                        ex_price = p["tp"] if r.high >= p["tp"] else p["sl"]
                        pnlR = (ex_price - p["entry"]) / p["rpu"]
                        log([ts.isoformat(), "EXIT_LONG", ex_price, "long", p["sl"], p["tp"], round(pnlR, 2)])
                        send(f"EXIT LONG @ {ex_price:.2f} | R={pnlR:.2f}")
                        state["loss_streak"] = 0 if pnlR >= 0 else state["loss_streak"] + 1
                        state["position"] = None
                else:
                    if r.high >= p["sl"] or r.low <= p["tp"]:
                        ex_price = p["tp"] if r.low <= p["tp"] else p["sl"]
                        pnlR = (p["entry"] - ex_price) / p["rpu"]
                        log([ts.isoformat(), "EXIT_SHORT", ex_price, "short", p["sl"], p["tp"], round(pnlR, 2)])
                        send(f"EXIT SHORT @ {ex_price:.2f} | R={pnlR:.2f}")
                        state["loss_streak"] = 0 if pnlR >= 0 else state["loss_streak"] + 1
                        state["position"] = None

            ok_cooldown = True
            if state["last_trade_iso"]:
                last = pd.Timestamp(state["last_trade_iso"])
                ok_cooldown = (ts - last) >= pd.Timedelta(hours=COOLDOWN_H)
            can_trade = (state["trades_today"] < MAX_TRADES_D) and ok_cooldown and (state["loss_streak"] < LOSS_STREAK_MAX)

            if (not state["position"]) and can_trade and atrv > 0:
                if r["ema_fast"] > r["ema_slow"] and px > r["don_high"]:
                    sl = px - 1.0 * atrv
                    tp = px + 2.0 * atrv
                    rpu = max(px - sl, 1e-9)
                    state["position"] = {"side": "long", "entry": px, "sl": sl, "tp": tp, "rpu": rpu}
                    state["last_trade_iso"] = ts.isoformat()
                    state["trades_today"] += 1
                    log([ts.isoformat(), "ENTRY_LONG", px, "long", sl, tp, 0.0])
                    send(f"ENTRY LONG @ {px:.2f} | SL={sl:.2f} TP={tp:.2f}")
                elif r["ema_fast"] < r["ema_slow"] and px < r["don_low"]:
                    sl = px + 1.0 * atrv
                    tp = px - 2.0 * atrv
                    rpu = max(sl - px, 1e-9)
                    state["position"] = {"side": "short", "entry": px, "sl": sl, "tp": tp, "rpu": rpu}
                    state["last_trade_iso"] = ts.isoformat()
                    state["trades_today"] += 1
                    log([ts.isoformat(), "ENTRY_SHORT", px, "short", sl, tp, 0.0])
                    send(f"ENTRY SHORT @ {px:.2f} | SL={sl:.2f} TP={tp:.2f}")

            save_state(state)

        except Exception as e:
            log([datetime.now(timezone.utc).isoformat(), "ERROR", 0, "-", 0, 0, str(e)])

        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
