import time
import pandas as pd
from datetime import datetime
from config import (
    symbols, timeframe, rsi_sell, use_zigzag_filter, use_god_candle_filter,
    min_entry_signals_required, enable_advanced_entry_strategies
)
from utils.exchange_utils import get_exchange, fetch_ohlcv_safe
from utils.indicators import calculate_indicators, evaluate_all_entry_conditions
from utils.bot_state import last_entry_info, last_exit_info

exchange = get_exchange()

def show_balance():
    try:
        balance = exchange.fetch_balance()
        usdt = balance['total'].get('USDT', 0)
        return f"💰 Total Balance: ${usdt:.2f}"
    except Exception as e:
        return f"❌ Error fetching balance: {e}"

def show_portfolio():
    try:
        balance = exchange.fetch_balance()
        lines = ["📊 Portfolio:"]
        for asset, data in balance['total'].items():
            if isinstance(data, (int, float)) and data > 0:
                lines.append(f"{asset}: {data:.4f}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error fetching portfolio: {e}"

def show_pnl():
    return "📉 PNL tracking not implemented yet."

def show_fees():
    return "💸 Fee tracking not implemented yet."

def show_max_drawdown():
    return "📉 Drawdown stats not implemented yet."

def show_open_positions():
    return "📈 Open positions tracking not implemented yet."

def show_position_details(symbol):
    try:
        pos = exchange.fetch_position(symbol)
        return f"📌 {symbol} Position:\n{pos}"
    except Exception as e:
        return f"❌ Error fetching position for {symbol}: {e}"

def show_pending_orders():
    try:
        lines = []
        for symbol in symbols:
            orders = exchange.fetch_open_orders(symbol)
            if orders:
                lines.append(f"📄 {symbol}: {len(orders)} open orders")
            else:
                lines.append(f"✅ {symbol}: No open orders")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error fetching orders: {e}"

def show_orderbook_snapshot(symbol):
    try:
        ob = exchange.fetch_order_book(symbol)
        bid = ob['bids'][0][0] if ob['bids'] else 0
        ask = ob['asks'][0][0] if ob['asks'] else 0
        spread = ask - bid
        return f"📘 {symbol} Orderbook:\nBid: {bid:.4f} | Ask: {ask:.4f} | Spread: {spread:.4f}"
    except Exception as e:
        return f"❌ Error fetching order book: {e}"

def recommend_symbol(pair):
    try:
        df15 = fetch_ohlcv_safe(pair, '15m')
        df1h = fetch_ohlcv_safe(pair, '1h')

        if isinstance(df15, list):
            df15 = pd.DataFrame(df15, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        if isinstance(df1h, list):
            df1h = pd.DataFrame(df1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        df15 = calculate_indicators(df15)
        df1h = calculate_indicators(df1h)

        passed, strategy, details = evaluate_all_entry_conditions(df15, df1h, config)
        if passed:
            return f"✅ {pair} is a recommended BUY.\nStrategy: {strategy}\nDetails: {details}"
        else:
            return f"❌ No signal for {pair}.\n{details}"
    except Exception as e:
        return f"❌ Error evaluating {pair}: {e}"

def get_scanner_results():
    results = []
    for sym in symbols:
        try:
            df15 = fetch_ohlcv_safe(sym, '15m')
            df1h = fetch_ohlcv_safe(sym, '1h')

            if isinstance(df15, list):
                df15 = pd.DataFrame(df15, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            if isinstance(df1h, list):
                df1h = pd.DataFrame(df1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            df15 = calculate_indicators(df15)
            df1h = calculate_indicators(df1h)

            passed, strategy, details = evaluate_all_entry_conditions(df15, df1h, config)
            if passed:
                results.append(f"✅ {sym} - {strategy} | {details}")
        except Exception as e:
            results.append(f"⚠️ {sym} failed to evaluate: {e}")
    return "\n".join(results) if results else "❌ No matching signals found."

def show_last_entry():
    if not last_entry_info.get("symbol"):
        return "❌ No recorded entry yet."
    return (
        f"🟢 Last Entry\n"
        f"Symbol: {last_entry_info['symbol']}\n"
        f"Time: {last_entry_info['time']}\n"
        f"Strategy: {last_entry_info.get('strategy', 'N/A')}\n"
        f"Details: {last_entry_info.get('details', '-')}"
    )

def show_last_close():
    if not last_exit_info.get("symbol"):
        return "❌ No recorded exit yet."
    return (
        f"🔴 Last Exit\n"
        f"Symbol: {last_exit_info['symbol']}\n"
        f"Time: {last_exit_info['time']}\n"
        f"Details: {last_exit_info.get('details', '-')}"
    )

def manual_buy(symbol, amount):
    try:
        order = exchange.create_market_buy_order(symbol, amount)
        return f"✅ Manual BUY executed for {symbol}: {amount}\n{order}"
    except Exception as e:
        return f"❌ Manual buy failed: {e}"

def manual_sell(symbol):
    try:
        order = exchange.create_market_sell_order(symbol, None)
        return f"✅ Manual SELL executed for {symbol}\n{order}"
    except Exception as e:
        return f"❌ Manual sell failed: {e}"

def manual_cancel(symbol):
    try:
        orders = exchange.fetch_open_orders(symbol)
        for order in orders:
            exchange.cancel_order(order['id'], symbol)
        return f"✅ Cancelled {len(orders)} orders for {symbol}."
    except Exception as e:
        return f"❌ Cancel failed: {e}"

def trigger_take_profit(symbol):
    return f"🚀 TP triggered manually for {symbol}"

def trigger_stop_loss(symbol):
    return f"🛑 SL triggered manually for {symbol}"
