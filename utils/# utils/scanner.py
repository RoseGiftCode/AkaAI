# utils/scanner.py

import ccxt
import time
from utils.exchange import get_top_volatile_tokens  # make sure this is correct
import config

# Global cache for scanner
volatile_cache = {}

def scanner_loop():
    exchange = ccxt.binance({
        "enableRateLimit": True,
        "options": {"adjustForTimeDifference": True}
    })

    while True:
        try:
            tokens = get_top_volatile_tokens(
                exchange,
                top_n=config.top_n_volatile,         # e.g. 5
                interval='15m',
                min_volume=config.min_volume,        # e.g. 500000
                min_change_percent=config.min_change_percent,  # e.g. 2
                max_price=config.max_price           # Optional
            )

            # ✅ Update global cache
            volatile_cache.clear()
            for symbol, percent, vol in tokens:
                volatile_cache[symbol] = {
                    "percent": percent,
                    "volume": vol
                }

            print("🔁 Updated volatile_cache:", volatile_cache)
        except Exception as e:
            print("⚠️ Volatile token scanner failed:", e)

        time.sleep(config.scan_interval)  # e.g. 60s
