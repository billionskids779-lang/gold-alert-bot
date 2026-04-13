"""
XAU/USD Telegram Alert Bot
Strategy : EMA 9/21 crossover + RSI 14 filter
Timeframe : M5 (checks every 5 minutes)
Data      : Yahoo Finance (free, no API key needed)
Alerts    : Telegram bot message to your phone
"""

import os
import time
import logging
from datetime import datetime
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import requests

# ─── CONFIG (set these as environment variables on Render) ──────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")

SYMBOL        = "GC=F"       # Gold futures on Yahoo Finance
INTERVAL      = "5m"         # M5 candles
CHECK_EVERY   = 300          # seconds (5 minutes)

EMA_FAST      = 9
EMA_SLOW      = 21
RSI_PERIOD    = 14
RSI_OB        = 65           # overbought — avoid buying above this
RSI_OS        = 35           # oversold  — avoid selling below this

SL_PIPS       = 15           # stop loss in pips  (1 pip gold = $1)
TP_PIPS       = 30           # take profit in pips (2:1 reward)

# ─── LOGGING ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("XAU_ALERT")

# ─── TELEGRAM ───────────────────────────────────────────────────────
def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            log.info("Telegram alert sent.")
        else:
            log.error(f"Telegram error {r.status_code}: {r.text}")
    except Exception as e:
        log.error(f"Telegram send failed: {e}")

# ─── DATA + STRATEGY ────────────────────────────────────────────────
def fetch_candles() -> pd.DataFrame | None:
    try:
        df = yf.download(SYMBOL, period="2d", interval=INTERVAL, progress=False)
        if df.empty or len(df) < EMA_SLOW + 5:
            log.warning("Not enough candle data.")
            return None
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.columns = ["open", "high", "low", "close", "volume"]
        df.dropna(inplace=True)
        return df
    except Exception as e:
        log.error(f"Data fetch error: {e}")
        return None

def compute_signal(df: pd.DataFrame) -> dict:
    df["ema_fast"] = ta.ema(df["close"], length=EMA_FAST)
    df["ema_slow"] = ta.ema(df["close"], length=EMA_SLOW)
    df["rsi"]      = ta.rsi(df["close"], length=RSI_PERIOD)
    df.dropna(inplace=True)

    if len(df) < 2:
        return {"signal": None}

    prev = df.iloc[-2]
    curr = df.iloc[-1]
    price = round(float(curr["close"]), 2)
    rsi   = round(float(curr["rsi"]), 1)

    cross_up   = prev["ema_fast"] <= prev["ema_slow"] and curr["ema_fast"] > curr["ema_slow"]
    cross_down = prev["ema_fast"] >= prev["ema_slow"] and curr["ema_fast"] < curr["ema_slow"]

    if cross_up and rsi < RSI_OB:
        return {"signal": "BUY",  "price": price, "rsi": rsi,
                "sl": round(price - SL_PIPS, 2), "tp": round(price + TP_PIPS, 2)}
    if cross_down and rsi > RSI_OS:
        return {"signal": "SELL", "price": price, "rsi": rsi,
                "sl": round(price + SL_PIPS, 2), "tp": round(price - TP_PIPS, 2)}

    return {"signal": None, "price": price, "rsi": rsi}

# ─── MESSAGE FORMATTER ──────────────────────────────────────────────
def format_alert(s: dict) -> str:
    direction = s["signal"]
    emoji     = "🟢" if direction == "BUY" else "🔴"
    action    = "BUY  (Long)" if direction == "BUY" else "SELL (Short)"
    now       = datetime.utcnow().strftime("%H:%M UTC")

    return (
        f"{emoji} <b>XAU/USD {action}</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📍 Entry    : <b>${s['price']}</b>\n"
        f"🛑 Stop loss: <b>${s['sl']}</b>  (–{SL_PIPS} pips)\n"
        f"🎯 Take profit: <b>${s['tp']}</b>  (+{TP_PIPS} pips)\n"
        f"📊 RSI      : {s['rsi']}\n"
        f"⏰ Signal at: {now}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"<i>Open MT5 → XAUUSDm → New Order</i>"
    )

# ─── MAIN LOOP ──────────────────────────────────────────────────────
def main():
    log.info("=" * 55)
    log.info("  XAU/USD Telegram Alert Bot — EMA9/21 + RSI14")
    log.info("=" * 55)
    send_telegram("✅ <b>XAU/USD Alert Bot is live!</b>\nWatching Gold M5 for signals...")

    last_signal = None   # avoid duplicate alerts on same signal

    while True:
        try:
            df = fetch_candles()
            if df is not None:
                result = compute_signal(df)
                sig    = result.get("signal")

                log.info(f"Price=${result.get('price')}  RSI={result.get('rsi')}  Signal={sig or 'HOLD'}")

                if sig and sig != last_signal:
                    msg = format_alert(result)
                    send_telegram(msg)
                    last_signal = sig
                elif not sig:
                    last_signal = None   # reset so next signal fires fresh

        except Exception as e:
            log.error(f"Main loop error: {e}")

        time.sleep(CHECK_EVERY)

if __name__ == "__main__":
    main()
