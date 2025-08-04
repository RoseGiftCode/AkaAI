def evaluate_all_entry_conditions(df15, df1h, config):
    import ta

    results = []
    score = 0

    try:
        price = df15['close'].iloc[-1]
        rsi_15 = df15['rsi'].iloc[-1]
        macd_hist_15 = df15['macd_hist'].iloc[-1]
        volume = df15['volume'].iloc[-1]
        lower_bb = df15['lower_band'].iloc[-1]

        avg_volume = df15['volume'].rolling(window=int(config.volume_lookback)).mean().iloc[-1]
        sma_1h = df1h['sma'].iloc[-1] if 'sma' in df1h.columns else 0
        price_trend = "Below SMA" if price < sma_1h else "Above SMA"

        # --- 1. Your Default Logic ---
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
            'passed': default_score >= 3,
            'details': f"RSI: {rsi_15:.2f}, MACD Hist: {macd_hist_15:.4f}, Price: {price:.4f}, BB: {lower_bb:.4f}, Vol: {volume:.0f} > Avg: {avg_volume:.0f}"
        })

        # --- 2. RSI + MACD ---
        cond1 = rsi_15 < 30
        cond2 = macd_hist_15 > 0
        results.append({
            'name': 'RSI + MACD',
            'score': cond1 + cond2,
            'passed': cond1 and cond2,
            'details': f"RSI: {rsi_15:.2f}, MACD Hist: {macd_hist_15:.4f}"
        })

        # --- 3. MACD + Volume ---
        cond3 = macd_hist_15 > 0
        cond4 = volume > avg_volume
        results.append({
            'name': 'MACD + Volume',
            'score': cond3 + cond4,
            'passed': cond3 and cond4,
            'details': f"MACD Hist: {macd_hist_15:.4f}, Volume: {volume:.0f} > Avg: {avg_volume:.0f}"
        })

        # --- 4. RSI + Bollinger Bands ---
        cond5 = rsi_15 < 30
        cond6 = price < lower_bb
        results.append({
            'name': 'RSI + Bollinger Bands',
            'score': cond5 + cond6,
            'passed': cond5 and cond6,
            'details': f"RSI: {rsi_15:.2f}, Price: {price:.4f} < Lower BB: {lower_bb:.4f}"
        })

        # --- Choose the best strategy ---
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
