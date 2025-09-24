import os, time, csv, json, requests
from datetime import datetime, timezone

# ---------------- Sicherheit: nur Paper-Mode ----------------
PAPER_MODE = os.getenv("PAPER_MODE", "1")   # default: an
LIVE_TRADING = os.getenv("LIVE_TRADING", "0")
if LIVE_TRADING == "1":
    raise SystemExit("❌ LIVE_TRADING=1 erkannt. Dieser Runner ist NUR für Paper Trading. Abbruch.")

# ---------------- Telegram (optional) ----------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

def _tg(msg: str):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
                timeout=10
            )
        except Exception as e:
            print("Telegram send fail:", e)

def _startup_ping():
    _tg("✅ Paper-Runner gestartet (nur Test, kein Geld).")

# ---------------- Datenablage ----------------
DATA_DIR   = "/data"
CSV_FILE   = os.path.join(DATA_DIR, "paper_trades.csv")
STATE_FILE = os.path.join(DATA_DIR, "state.json")

def ensure_data():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="") as f:
            csv.writer(f).writerow(["ts_iso","action","price","note"])
    if not os.path.exists(STATE_FILE):
        with open(STATE_FILE, "w") as f:
            json.dump({"last_start": None}, f)

def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.loads(f.read() or "{}")
    except Exception:
        return {"last_start": None}

def save_state(s):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f)

# ---------------- Dummy-Strategie (reine Simulation) ----------------
def log_trade(action, price, note):
    ts = datetime.now(timezone.utc).isoformat()
    with open(CSV_FILE, "a", newline="") as f:
        csv.writer(f).writerow([ts, action, f"{price:.2f}", note])
    print(f"{ts} | {action:<4} | px={price:.2f} | {note}")

def decide_and_papertrade():
    # reine Demo: schreibt jede Minute eine Zeile (hier später echte Logik einhängen)
    fake_price = 10000.0
    log_trade("HOLD", fake_price, "demo-tick")

# ---------------- Main ----------------
def main():
    ensure_data()
    _startup_ping()
    st = load_state()
    st["last_start"] = datetime.now(timezone.utc).isoformat()
    save_state(st)

    print("🚀 Paper Trading Simulation aktiv – echtes Geld ist AUS.")
    while True:
        decide_and_papertrade()
        time.sleep(60)  # 1-Minuten-Takt

if __name__ == "__main__":
    main()

