# src/utils/indicators.py
import pandas as pd
import numpy as np
import ta  # pip install ta
import config


def calculate_zigzag(prices, deviation=5):
    zigzag_points = []
    last_extreme = prices[0]
    trend = None

    for i in range(1, len(prices)):
        change = (prices[i] - last_extreme) / last_extreme * 100

        if trend is None:
            if abs(change) >= deviation:
                trend = 'up' if change > 0 else 'down'
                last_extreme = prices[i]
                zigzag_points.append({'index': i, 'type': 'bottom' if trend == 'up' else 'top'})
        else:
            if trend == 'up':
                if prices[i] > last_extreme:
                    last_extreme = prices[i]
                elif (last_extreme - prices[i]) / last_extreme * 100 >= deviation:
                    trend = 'down'
                    last_extreme = prices[i]
                    zigzag_points.append({'index': i, 'type': 'top'})
            elif trend == 'down':
                if prices[i] < last_extreme:
                    last_extreme = prices[i]
                elif (prices[i] - last_extreme) / last_extreme * 100 >= deviation:
                    trend = 'up'
                    last_extreme = prices[i]
                    zigzag_points.append({'index': i, 'type': 'bottom'})
    return zigzag_points

def calculate_indicators(df):
    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['open'] = df['open'].astype(float)
    df['volume'] = df['volume'].astype(float)

    df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()
    macd = ta.trend.MACD(close=df['close'])
    df['macd_hist'] = macd.macd_diff()
    bb = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
    df['upper_band'] = bb.bollinger_hband()
    df['middle_band'] = bb.bollinger_mavg()
    df['lower_band'] = bb.bollinger_lband()
    df['volume_avg'] = df['volume'].rolling(window=20).mean()
    df['zigzag'] = detect_zigzag(df)
    df['god_candle'] = detect_god_candle(df)

    return df

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

def detect_god_candle(df, lookback=5, threshold=2.0):
    bodies = (df['close'] - df['open']).abs()
    god_candle_flags = [False] * len(df)
    for i in range(lookback, len(df)):
        avg_body = bodies[i - lookback:i].mean()
        current_body = bodies[i]
        god_candle_flags[i] = current_body > (avg_body * threshold)
    return god_candle_flags

def is_volume_spike(df, window=20, multiplier=1.5):
    if len(df) < window + 1:
        return False
    avg_volume = df['volume'].iloc[-(window + 1):-1].mean()
    current_volume = df['volume'].iloc[-1]
    return current_volume > avg_volume * multiplier

def get_rsi(close):
    return ta.momentum.RSIIndicator(close=close, window=14).rsi()

def get_macd(close):
    macd = ta.trend.MACD(close=close)
    return macd.macd(), macd.macd_signal(), macd.macd_diff()

def get_bollinger_bands(close):
    bb = ta.volatility.BollingerBands(close=close, window=20, window_dev=2)
    return bb.bollinger_hband(), bb.bollinger_mavg(), bb.bollinger_lband()

def is_god_candle(df):
    flags = detect_god_candle(df)
    return flags[-1] if flags else False

def get_sma(close, period):
    return ta.trend.SMAIndicator(close=close, window=period).sma_indicator()

def evaluate_all_entry_conditions(df15, df1h, config):
    results = []
    try:
        price = df15['close'].iloc[-1]
        rsi_15 = df15['rsi'].iloc[-1]
        macd_hist_15 = df15['macd_hist'].iloc[-1]
        volume = df15['volume'].iloc[-1]
        lower_bb = df15['lower_band'].iloc[-1]

        avg_volume = df15['volume'].rolling(window=int(config.volume_lookback)).mean().iloc[-1]
        sma_1h = df1h['sma'].iloc[-1] if 'sma' in df1h.columns else 0
        price_trend = "Below SMA" if price < sma_1h else "Above SMA"

        default_conditions = [
            rsi_15 < 30,
            macd_hist_15 > 0,
            price < lower_bb,
            volume > avg_volume,
        ]
        default_score = sum(default_conditions)
        results.append({
            'name': 'Default Logic',
            'score': default_score,
            'passed': default_score >= config.min_entry_signals_required,
            'details': f"RSI: {rsi_15:.2f}, MACD Hist: {macd_hist_15:.4f}, Price: {price:.4f}, BB: {lower_bb:.4f}, Vol: {volume:.0f} > Avg: {avg_volume:.0f}"
        })

        cond1 = rsi_15 < 30
        cond2 = macd_hist_15 > 0
        results.append({
            'name': 'RSI + MACD',
            'score': cond1 + cond2,
            'passed': cond1 and cond2,
            'details': f"RSI: {rsi_15:.2f}, MACD Hist: {macd_hist_15:.4f}"
        })

        cond3 = macd_hist_15 > 0
        cond4 = volume > avg_volume
        results.append({
            'name': 'MACD + Volume',
            'score': cond3 + cond4,
            'passed': cond3 and cond4,
            'details': f"MACD Hist: {macd_hist_15:.4f}, Volume: {volume:.0f} > Avg: {avg_volume:.0f}"
        })

        cond5 = rsi_15 < 30
        cond6 = price < lower_bb
        results.append({
            'name': 'RSI + Bollinger Bands',
            'score': cond5 + cond6,
            'passed': cond5 and cond6,
            'details': f"RSI: {rsi_15:.2f}, Price: {price:.4f} < Lower BB: {lower_bb:.4f}"
        })

        best = sorted(
            [r for r in results if r['passed']],
            key=lambda x: (x['score'], x['name']), reverse=True
        )

        if best:
            best_strategy = best[0]
            return True, best_strategy['name'], f"{best_strategy['details']} | Score: {best_strategy['score']} | Trend: {price_trend}"
        else:
            return False, None, "❌ No entry condition met in any strategy."

    except Exception as e:
        return False, None, f"⚠️ Error evaluating entry conditions: {e}"
