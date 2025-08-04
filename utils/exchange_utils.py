# utils/exchange_utils.py

import ccxt
from config import mexc_api_key, mexc_api_secret
import json
import os

# Initialize MEXC Exchange
exchange = ccxt.mexc({
    'apiKey': mexc_api_key,
    'secret': mexc_api_secret,
    'enableRateLimit': True
})

def validate_api_keys():
    try:
        balance = exchange.fetch_balance()
        usdt = balance['free'].get('USDT', 0)
        print(f"✅ API valid. Free USDT: {usdt:.2f}")
    except Exception as e:
        print(f"❌ API error: {e}")
        exit(1)

# Save and load daily loss
DAILY_LOSS_FILE = 'daily_loss.json'

def load_daily_loss():
    if os.path.exists(DAILY_LOSS_FILE):
        with open(DAILY_LOSS_FILE, 'r') as f:
            return json.load(f)
    return {'loss': 0, 'starting_balance': 160}

def save_daily_loss(data):
    with open(DAILY_LOSS_FILE, 'w') as f:
        json.dump(data, f, indent=2)


# Return the initialized exchange object
def get_exchange():
    return exchange

# Safe OHLCV fetch wrapper
def fetch_ohlcv_safe(symbol, timeframe='1h', limit=100):
    try:
        return exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    except Exception as e:
        print(f"⚠️ OHLCV fetch error for {symbol} ({timeframe}): {e}")
        return None

