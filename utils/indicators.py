import pandas as pd
import numpy as np
import ta
import config


# === 1. Fetch Data ===
def fetch_ohlcv(symbol, timeframe):
    from exchange import exchange  # Or however you load your exchange instance
    data = exchange.fetch_ohlcv(symbol, timeframe)
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df


# === 2. Add Indicators ===
def add_indicators(df):
    df = df.copy()
    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['open'] = df['open'].astype(float)
    df['volume'] = df['volume'].astype(float)

    # RSI
    df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()

    # MACD Histogram
    macd = ta.trend.MACD(close=df['close'])
    df['macd_hist'] = macd.macd_diff()

    # Bollinger Bands
    bb = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
    df['upper_band'] = bb.bollinger_hband()
    df['middle_band'] = bb.bollinger_mavg()
    df['lower_band'] = bb.bollinger_lband()

    # SMA
    df['sma'] = ta.trend.SMAIndicator(close=df['close'], window=50).sma_indicator()

    # Volume
    df['volume_avg'] = df['volume'].rolling(window=config.volume_lookback).mean()

    # Custom
    df['zigzag'] = detect_zigzag(df)
    df['god_candle'] = detect_god_candle(df)

    return df


# === 3. Zigzag Detection ===
def detect_zigzag(df, depth=5):
    result = [0] * len(df)
    for i in range(depth, len(df) - depth):
        is_top = all(df['high'][i] > df['high'][i - j] and df['high'][i] > df['high'][i + j] for j in range(1, depth + 1))
        is_bottom = all(df['low'][i] < df['low'][i - j] and df['low'][i] < df['low'][i + j] for j in range(1, depth + 1))
        if is_top:
            result[i] = 1
        elif is_bottom:
            result[i] = -1
    return result


# === 4. God Candle Detection ===
def detect_god_candle(df, lookback=5, threshold=2.0):
    bodies = (df['close'] - df['open']).abs()
    god_candle_flags = [False] * len(df)
    for i in range(lookback, len(df)):
        avg_body = bodies[i - lookback:i].mean()
        current_body = bodies[i]
        god_candle_flags[i] = current_body > (avg_body * threshold)
    return god_candle_flags


# === 5. Entry Condition Evaluator ===
def evaluate_all_entry_conditions(df15, df1h, config):
    results = []
    try:
        price = df15['close'].iloc[-1]
        rsi_15 = df15['rsi'].iloc[-1]
        macd_hist_15 = df15['macd_hist'].iloc[-1]
        volume = df15['volume'].iloc[-1]
        lower_bb = df15['lower_band'].iloc[-1]
        avg_volume = df15['volume_avg'].iloc[-1]
        sma_1h = df1h['sma'].iloc[-1] if 'sma' in df1h.columns else 0
        price_trend = "Below SMA" if price < sma_1h else "Above SMA"

        # Default Strategy
        default_conditions = [
            rsi_15 < 30 if pd.notna(rsi_15) else False,
            macd_hist_15 > 0 if pd.notna(macd_hist_15) else False,
            price < lower_bb if pd.notna(lower_bb) else False,
            volume > avg_volume if pd.notna(avg_volume) else False
        ]
        default_score = sum(default_conditions)
        results.append({
            'name': 'Default Logic',
            'score': default_score,
            'passed': default_score >= config.min_entry_signals_required,
            'details': f"RSI: {rsi_15:.2f}, MACD Hist: {macd_hist_15:.4f}, Price: {price:.4f}, BB: {lower_bb:.4f}, Vol: {volume:.0f} > Avg: {avg_volume:.0f}"
        })

        # Strategy 2: RSI + MACD
        cond1 = rsi_15 < 30 if pd.notna(rsi_15) else False
        cond2 = macd_hist_15 > 0 if pd.notna(macd_hist_15) else False
        results.append({
            'name': 'RSI + MACD',
            'score': cond1 + cond2,
            'passed': cond1 and cond2,
            'details': f"RSI: {rsi_15:.2f}, MACD Hist: {macd_hist_15:.4f}"
        })

        # Strategy 3: MACD + Volume
        cond3 = macd_hist_15 > 0 if pd.notna(macd_hist_15) else False
        cond4 = volume > avg_volume if pd.notna(avg_volume) else False
        results.append({
            'name': 'MACD + Volume',
            'score': cond3 + cond4,
            'passed': cond3 and cond4,
            'details': f"MACD Hist: {macd_hist_15:.4f}, Volume: {volume:.0f} > Avg: {avg_volume:.0f}"
        })

        # Strategy 4: RSI + Bollinger Bands
        cond5 = rsi_15 < 30 if pd.notna(rsi_15) else False
        cond6 = price < lower_bb if pd.notna(lower_bb) else False
        results.append({
            'name': 'RSI + Bollinger Bands',
            'score': cond5 + cond6,
            'passed': cond5 and cond6,
            'details': f"RSI: {rsi_15:.2f}, Price: {price:.4f} < Lower BB: {lower_bb:.4f}"
        })

        # Best Strategy Selection
        best = sorted(
            [r for r in results if r['passed']],
            key=lambda x: (x['score'], x['name']),
            reverse=True
        )

        if best:
            best_strategy = best[0]
            return True, best_strategy['name'], f"{best_strategy['details']} | Score: {best_strategy['score']} | Trend: {price_trend}"
        else:
            return False, None, "❌ No entry condition met in any strategy."

    except Exception as e:
        return False, None, f"⚠️ Error evaluating entry conditions: {e}"


# === 6. Helpers (Optional) ===
def is_volume_spike(df, window=20, multiplier=1.5):
    if len(df) < window + 1:
        return False
    avg_volume = df['volume'].iloc[-(window + 1):-1].mean()
    current_volume = df['volume'].iloc[-1]
    return current_volume > avg_volume * multiplier


def is_god_candle(df):
    flags = detect_god_candle(df)
    return flags[-1] if flags else False
