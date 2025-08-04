import ccxt, time

def get_top_volatile_tokens(exchange, top_n=1, interval='15m', min_volume=500000, min_change_percent=2, max_price=None):
    try:
        markets = exchange.load_markets()
    except Exception as e:
        print(f"⚠️ Failed to load markets: {e}")
        return []

    usdt_pairs = [s for s in markets if s.endswith('/USDT') and markets[s].get('active', False)]
    volatile_tokens = []

    for symbol in usdt_pairs:
        try:
            ticker = exchange.fetch_ticker(symbol)
            percent = ticker.get('percentage', 0)
            vol = ticker.get('quoteVolume', 0)
            price = ticker.get('last', 0)

            if percent >= min_change_percent and vol >= min_volume:
                if price and (max_price is None or price <= max_price):
                    volatile_tokens.append((symbol, percent, vol))
        except Exception:
            continue  # Ignore symbols that fail

        time.sleep(exchange.rateLimit / 1000)

    # Sort by percent change descending
    volatile_tokens.sort(key=lambda x: x[1], reverse=True)
    return volatile_tokens[:top_n]
