# ✅ utils/helpers.py

def safe_fetch_balance(exchange):
    try:
        return exchange.fetch_balance()
    except Exception as e:
        print("❌ Failed to fetch balance:", e)
        return {}

def safe_fetch_ticker(exchange, symbol):
    try:
        return exchange.fetch_ticker(symbol)
    except Exception as e:
        print(f"❌ Failed to fetch ticker for {symbol}:", e)
        return {"last": 0, "bid": 0, "ask": 0}

def format_usdt(value):
    try:
        return f"${float(value):,.2f}"
    except:
        return "$0.00"

def format_pct(value):
    try:
        return f"{float(value):.2f}%"
    except:
        return "0.00%"

def try_get(d, key, default=None):
    try:
        return d.get(key, default)
    except:
        return default
