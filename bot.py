import os
import time
import json
import shutil
import pandas as pd
from datetime import datetime
import threading
import logging
from logging.handlers import RotatingFileHandler

import ccxt
import ta
import config

# ✅ Import indicator functions
from utils.indicators import (
    calculate_indicators,
    detect_zigzag,
    detect_god_candle,
    get_rsi,
    get_macd,
    get_bollinger_bands,
    is_god_candle,
    is_volume_spike,
    get_sma
)

# ✅ Import Telegram notifier
from utils.telegram import notify

# ✅ Import volatility scanner
from utils.volatility_detector import get_top_volatile_tokens

# ✅ Import exchange + daily loss logic
from utils.exchange_utils import exchange, validate_api_keys, load_daily_loss

# ✅ Import bot status controller
from utils.bot_state import is_bot_active

import importlib

import threading


# Start Telegram command loop
threading.Thread(
    target=lambda: importlib.import_module("utils.telegram_command_poll").telegram_command_loop(),
    daemon=True
).start()



# New features (unchanged)
def volume_spike_vs_avg(df, lookback=20):
    try:
        avg_volume = df['volume'].rolling(window=lookback).mean().iloc[-2]
        current_volume = df['volume'].iloc[-1]
        return current_volume > avg_volume, current_volume, avg_volume
    except Exception as e:
        logging.error(f"Volume avg check error: {e}")
        return False, 0, 0

def should_exit_stale_trade(entry_time, max_duration_minutes=60):
    if not entry_time:
        return False
    try:
        now = time.time()
        return (now - entry_time) > (max_duration_minutes * 60)
    except:
        return False


def log_missed_trade_conditions(symbol, df15, reason, df1h=None):
    try:
        rsi = df15['rsi'].iloc[-1]
        macd = df15['macd'].iloc[-1]
        signal = df15['signal'].iloc[-1]
        price = df15['close'].iloc[-1]
        volume = df15['volume'].iloc[-1]
        avg_volume = df15['volume'].rolling(window=int(config.volume_lookback)).mean().iloc[-1]
        atr = ta.volatility.AverageTrueRange(
            high=df15['high'], low=df15['low'], close=df15['close'], window=config.atr_period
        ).average_true_range().iloc[-1]
        
        sma_1h = df1h['sma'].iloc[-1] if df1h is not None else 0
        rsi_1h = df1h['rsi'].iloc[-1] if df1h is not None else 0
        trend = "Below SMA" if price < sma_1h else "Above SMA" if sma_1h > 0 else "Unknown"

        # Soft filter: only log if RSI shows some trade relevance
        rsi_tolerance_zone = any(abs(rsi - lvl) <= 5 for lvl in RSI_LEVELS)
        if rsi < 40 or rsi_tolerance_zone:
            message = (
                f"🚫 No Entry Signal for {symbol} @ RSI {rsi:.2f}\n"
                f"❌ No entry condition met in any strategy.\n"
                f"🔹 Reason: {reason}\n"
                f"🔸 RSI(15m): {rsi:.2f} | RSI(1h): {rsi_1h:.2f}\n"
                f"🔸 MACD(15m): {macd:.4f}/{signal:.4f}\n"
                f"🔸 Price: {price:.4f} | Lower BB: {df15['lower_band'].iloc[-1]:.4f}\n"
                f"🔸 Volume: {volume:.0f} / Avg: {avg_volume:.0f}\n"
                f"🔸 ATR: {atr:.4f}\n"
                f"🔸 SMA Trend: {trend} (1h SMA: {sma_1h:.4f})\n"
                f"🔸 Daily Loss: ${daily_loss['loss']:.2f} | Remaining: ${(config.max_daily_loss_percent / 100 * daily_loss['starting_balance']) - daily_loss['loss']:.2f}"
            )
            notify(message)
            logger.info(message)
        else:
            logger.info(f"⚠️ Skipped logging poor setup for {symbol} | RSI too high: {rsi:.2f} | Reason: {reason}")
    except Exception as e:
        logger.warning(f"⚠️ Logging missed entry failed for {symbol}: {e}")


def add_atr_to_telegram(symbol, atr):
    try:
        notify(f"📊 ATR for {symbol}: {atr:.4f}")
    except Exception as e:
        logging.warning(f"Failed to send ATR info: {e}")

def price_moved_too_far(entry_signal_price, current_price, max_distance_percent=2):
    try:
        diff = abs(current_price - entry_signal_price) / entry_signal_price
        return diff > (max_distance_percent / 100)
    except:
        return False

def filter_trend_with_rsi(df1h, rsi_threshold=65):
    try:
        rsi_1h = get_rsi(df1h['close']).iloc[-1]
        return rsi_1h < rsi_threshold
    except:
        return True

# Logging (unchanged)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[RotatingFileHandler('bot.log', maxBytes=10*1024*1024, backupCount=5), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

from collections import defaultdict
no_entry_alerts_sent = defaultdict(float)

# Exchange (unchanged)
try:
    exchange = ccxt.mexc({
        'apiKey': config.mexc_api_key,
        'secret': config.mexc_api_secret,
        'enableRateLimit': True
    })
    logger.info(f"✅ Using exchange: {exchange.id}")
    logger.info(f"fetchOHLCV supported: {exchange.has.get('fetchOHLCV')}")
    logger.info(f"Available timeframes: {exchange.timeframes}")
except Exception as e:
    logger.error(f"Init failed: {e}")
    notify(f"❌ Init failed: {e}")
    exit(1)

# Config (unchanged, references config.py with tp_multipliers)
try:
    RSI_LEVELS = config.rsi_entry_zones
    RSI_TOLERANCE = getattr(config, 'rsi_tolerance', 2)
    MAX_CONCURRENT_TRADES = getattr(config, 'max_concurrent_trades', 1)
    TRADE_COOLDOWN_SEC = getattr(config, 'trade_cooldown_sec', 300)
    MINIMUM_BALANCE = getattr(config, 'minimum_balance', 0.01)
    PERCENT_PER_TRADE = getattr(config, 'percent_per_trade', 1.0)
    MIN_TRADE_USDT = getattr(config, 'min_trade_usdt', 0.01)
    MAX_TRADE_USDT = getattr(config, 'max_trade_usdt', 50)
    TP_MULTIPLIERS = config.tp_multipliers
    RSI_SELL = config.rsi_sell
except AttributeError as e:
    logger.error(f"Missing config var: {e}")
    notify(f"❌ Missing config var: {e}")
    exit(1)

# Daily loss tracking (unchanged)
daily_loss = {'date': '', 'loss': 0.0, 'starting_balance': 0.0}
DAILY_LOSS_FILE = 'daily_loss.json'

OPEN_POSITIONS_FILE = 'open_positions.json'
RSI_ALERTS_FILE = 'rsi_alerts_sent.json'
LAST_TRADE_FILE = 'last_trade_time.json'
BACKUP_DIR = 'backups'
os.makedirs(BACKUP_DIR, exist_ok=True)

def load_json(fn):
    try:
        return json.load(open(fn)) if os.path.exists(fn) else {}
    except Exception as e:
        logger.error(f"Error loading {fn}: {e}")
        notify(f"⚠️ Error loading {fn}: {e}")
        return {}

def save_json(fn, data):
    try:
        if os.path.exists(fn):
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            shutil.copy(fn, os.path.join(BACKUP_DIR, f"{os.path.basename(fn)}_{ts}.bak"))
        tmp = fn + '.tmp'
        json.dump(data, open(tmp, 'w'), indent=2)
        os.replace(tmp, fn)
    except Exception as e:
        logger.error(f"Error saving {fn}: {e}")
        notify(f"⚠️ Error saving {fn}: {e}")

def load_daily_loss():
    try:
        data = json.load(open(DAILY_LOSS_FILE)) if os.path.exists(DAILY_LOSS_FILE) else {}
        today = datetime.now().strftime('%Y-%m-%d')
        if data.get('date') != today:
            return {'date': today, 'loss': 0.0, 'starting_balance': safe_fetch_balance()['free'].get('USDT', 0)}
        return data
    except Exception as e:
        logger.error(f"Error loading daily loss: {e}")
        return {'date': datetime.now().strftime('%Y-%m-%d'), 'loss': 0.0, 'starting_balance': safe_fetch_balance()['free'].get('USDT', 0)}

def save_daily_loss():
    save_json(DAILY_LOSS_FILE, daily_loss)

rsi_alerts_sent = load_json(RSI_ALERTS_FILE)
open_positions = load_json(OPEN_POSITIONS_FILE)
last_trade_time = load_json(LAST_TRADE_FILE)

def save_state():
    save_json(OPEN_POSITIONS_FILE, open_positions)
    save_json(RSI_ALERTS_FILE, rsi_alerts_sent)
    save_json(LAST_TRADE_FILE, last_trade_time)

def safe_fetch_ohlcv(symbol, tf, max_retries=3, delay=5):
    for attempt in range(max_retries):
        try:
            data = exchange.fetch_ohlcv(symbol, tf)
            if isinstance(data, list):
                df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                return df
            return None
        except Exception as e:
            error_message = str(e)
            if hasattr(e, 'response'):
                error_message += f"\nResponse: {e.response.text}"
            elif hasattr(e, 'status'):
                error_message += f"\nStatus: {e.status}"
            elif hasattr(e, 'code'):
                error_message += f"\nCode: {e.code}"
            logger.error(f"{symbol} {tf} fetch error on attempt {attempt + 1}: {error_message}")
            if '429' in error_message or '403' in error_message or 'rate limit' in error_message.lower():
                logger.warning(f"Rate limit or forbidden error detected. Sleeping for 60 seconds...")
                time.sleep(60)
            else:
                time.sleep(delay)
    logger.error(f"❌ Failed to fetch OHLCV for {symbol} ({tf}) after {max_retries} attempts.")
    return None

def safe_fetch_ticker(symbol, retries=3, delay=2):
    for attempt in range(retries):
        try:
            t = exchange.fetch_ticker(symbol)
            if not t or 'bid' not in t or 'ask' not in t:
                raise ValueError("Invalid ticker")
            return t
        except Exception as e:
            logger.error(f"{symbol} ticker error: {e}")
            notify(f"⚠️ {symbol} ticker error: {e}")
            if attempt < retries - 1:
                time.sleep(delay * 2**attempt)
    return None

def can_trade_now(symbol):
    return (time.time() - last_trade_time.get(symbol, 0)) >= TRADE_COOLDOWN_SEC

def validate_symbol(symbol):
    try:
        mk = exchange.load_markets()
        if symbol not in mk or not mk[symbol]['active']:
            notify(f"⚠️ {symbol} not tradable")
            return False, None
        prec = mk[symbol]['precision']['amount']
        return True, prec
    except Exception as e:
        logger.error(f"validate_symbol {symbol}: {e}")
        notify(f"⚠️ validate_symbol {symbol}: {e}")
        return False, None

def prepare_indicators(df):
    if df is None or df.empty or len(df) < 50:
        print("Not enough data to calculate indicators.")
        return df, False
    df = df.copy()
    df.reset_index(drop=True, inplace=True)
    try:
        return df, True
    except Exception as e:
        print(f"Error calculating indicators: {e}")
        return df, False

def get_adaptive_rsi_levels(df, base_levels, atr_multiplier=1.5, atr_period=14):
    try:
        atr = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=atr_period).average_true_range().iloc[-1]
        price = df['close'].iloc[-1]
        atr_ratio = atr / price
        scale = 1 + atr_ratio * atr_multiplier
        adaptive_levels = [min(max(int(lvl * scale), 10), 50) for lvl in base_levels]
        return adaptive_levels
    except Exception as e:
        logger.error(f"Failed to calculate adaptive RSI levels: {e}")
        return base_levels

def check_indicators(df15, df1h):
    rsi = df15['rsi'].iloc[-1]
    macd = df15['macd'].iloc[-1]
    signal_macd = df15['signal'].iloc[-1]
    upper_band = df15['upper_band'].iloc[-1]
    lower_band = df15['lower_band'].iloc[-1]
    close = df15['close'].iloc[-1]
    volume = df15['volume'].iloc[-1]
    prev_volume = df15['volume'].iloc[-2]
    rsi_cond = rsi < 30
    macd_cond = macd > signal_macd
    boll_cond = close <= lower_band
    vol_cond = volume > prev_volume
    sma_1h = get_sma(df1h['close'], config.sma_period).iloc[-1]
    trend_cond = close < sma_1h * 1.01
    signal = ''
    if rsi_cond and macd_cond and boll_cond and vol_cond and trend_cond:
        signal = 'buy'
    elif not rsi_cond and macd < signal_macd and close >= upper_band and vol_cond:
        signal = 'sell'
    if is_god_candle(df15):
        return True, signal
    true_count = sum([rsi_cond, macd_cond, boll_cond, vol_cond])
    if true_count >= 3 and trend_cond:
        return True, signal
    if true_count == 2 and rsi_cond and vol_cond and trend_cond:
        return True, signal
    return False, signal

def get_adaptive_rsi_sell(df, base=70, multiplier=1.5, min_rsi=60, max_rsi=80, atr_period=14):
    try:
        atr = ta.volatility.AverageTrueRange(
            high=df['high'], low=df['low'], close=df['close'], window=atr_period
        ).average_true_range().iloc[-1]
        price = df['close'].iloc[-1]
        atr_ratio = atr / price
        adaptive_rsi = base + (atr_ratio * 100 * multiplier)
        return max(min_rsi, min(int(adaptive_rsi), max_rsi))
    except Exception as e:
        logger.error(f"Error in adaptive RSI SELL: {e}")
        return base

def is_hammer_candle(df):
    try:
        c = df['close'].iloc[-1]
        o = df['open'].iloc[-1]
        h = df['high'].iloc[-1]
        l = df['low'].iloc[-1]
        body = abs(c - o)
        candle_range = h - l
        lower_wick = min(c, o) - l
        upper_wick = h - max(c, o)
        if candle_range == 0:
            return False
        body_ratio = body / candle_range
        lower_wick_ratio = lower_wick / candle_range
        upper_wick_ratio = upper_wick / candle_range
        return (body_ratio <= 0.3 and lower_wick_ratio >= 0.5 and upper_wick_ratio <= 0.1)
    except Exception as e:
        logger.error(f"Hammer detection error: {e}")
        return False

_last_good_balance = {'free': {'USDT': 0}}

def safe_fetch_balance():
    global _last_good_balance
    try:
        balance = exchange.fetch_balance()
        _last_good_balance = balance
        return balance
    except Exception as e:
        notify(f"⚠️ fetch_balance error: {e}")
        return _last_good_balance


tp_order_cancelled_time = {}  # ⬅ Store timestamps of last TP cancels


tp_order_cancelled_time = {}  # global store for cancel times

def monitor_orders(symbol):
    try:
        if not symbol:
            logger.warning("⚠️ monitor_orders called without a symbol.")
            return

        open_orders = exchange.fetch_open_orders(symbol)

        pos = open_positions.get(symbol, {})
        if not pos:
            return

        expected_tps = pos.get('tp_prices', [])
        if not expected_tps:
            return

        active_tp_prices = [float(order['price']) for order in open_orders if order['side'] == 'sell']

        for tp in expected_tps:
            if all(abs(tp - active_price) > 0.001 for active_price in active_tp_prices):
                tp_order_cancelled_time[symbol] = time.time()
                logger.info(f"🛑 Manual TP cancel detected for {symbol} at TP {tp:.4f} — pausing TP for 60s")
                break

    except Exception as e:
        logger.warning(f"⚠️ monitor_orders failed for {symbol or 'Unknown'}: {e}")




def set_take_profit(symbol, pos, api, logger):
    try:
        # 🚫 Respect delay after manual cancel
        now = time.time()
        delay = getattr(config, "tp_reset_delay_sec", 60)
        if symbol in tp_order_cancelled_time and now - tp_order_cancelled_time[symbol] < delay:
            logger.info(f"⏳ Skipping TP setup for {symbol}, still in 60s delay window after cancel")
            return

        df15 = safe_fetch_ohlcv(symbol, '15m')
        if df15 is None or df15.empty:
            logger.warning(f"No OHLCV data for {symbol} in set_take_profit")
            return

        atr = ta.volatility.AverageTrueRange(
            high=df15['high'], low=df15['low'], close=df15['close'], window=config.atr_period
        ).average_true_range().iloc[-1]

        pos['tp_prices'] = []
        market = api.markets.get(symbol, {})
        min_cost = market.get('limits', {}).get('cost', {}).get('min', 1.0)  # Fallback = 1 USDT

        for i, mult in enumerate(config.tp_multipliers):
            tp_price = pos['entry_price'] + (atr * mult)
            qty = pos['qty'] * (0.5 if i < len(config.tp_multipliers) - 1 else 1.0)
            order_value = qty * tp_price

            if order_value < min_cost:
                logger.warning(f"⚠️ TP {i+1} for {symbol} skipped: order value {order_value:.4f} < min cost {min_cost} USDT")
                continue

            api.create_limit_sell_order(symbol, qty, tp_price)
            pos['tp_prices'].append(tp_price)
            logger.info(f"✅ Set TP {i+1} for {symbol}: {qty} at {tp_price:.4f}")

        save_state()

    except Exception as e:
        logger.error(f"set_take_profit {symbol}: {e}")
        notify(f"⚠️ set_take_profit {symbol}: {e}")


def sync_positions():
    try:
        bal = safe_fetch_balance()
        usdt = bal['free'].get('USDT', 0)
        if usdt < MINIMUM_BALANCE:
            notify(f"⚠️ Low USDT: {usdt}")
        actual = {}
        for sym in config.symbols:
            asset = sym.split('/')[0]
            qty = bal['free'].get(asset, 0)
            if qty > 0:
                tk = safe_fetch_ticker(sym)
                if tk:
                    df15 = safe_fetch_ohlcv(sym, '15m')
                    atr = ta.volatility.AverageTrueRange(
                        high=df15['high'],
                        low=df15['low'],
                        close=df15['close'],
                        window=14
                    ).average_true_range().iloc[-1] if df15 is not None and not df15.empty else 0
                    
                    recent_cancel = tp_order_cancelled_time.get(sym, 0)
                    if time.time() - recent_cancel < 60:
                        logger.info(f"⏸️ Skipping TP setup for {sym}, recent manual cancel within 60s")
                        continue  # Delay TP reset

                    actual[sym] = {
                        'entry_price': tk['last'],
                        'qty': qty,
                        'highest_price': tk['last'],
                        'stop_loss': tk['last'] - (atr * config.stop_loss_atr_multiplier),
                        'tps_triggered': [],
                        'tp_prices': []
                    }

                    set_take_profit(sym, actual[sym], exchange, logger)
        for sym in list(open_positions):
            if sym not in actual:
                open_positions.pop(sym, None)
        open_positions.update(actual)
        save_state()
    except Exception as e:
        notify(f"⚠️ sync_positions: {e}")


def close_position(symbol, qty, price, reason):
    try:
        bal = exchange.fetch_balance()
        avail = bal['free'].get(symbol.split('/')[0], 0)
        if qty > avail: qty = avail
        if qty <= 0:
            open_positions.pop(symbol, None)
            save_state()
            return
        mk = exchange.load_markets()
        prec = mk[symbol]['precision']['amount']
        qty = round(qty, prec)
        order = exchange.create_market_sell_order(symbol, qty)
        fill_status = f"Filled: {order['filled'] / qty * 100:.0f}%" if order.get('filled') else "Unknown"
        pos = open_positions.get(symbol, {})
        entry_price = pos.get('entry_price', price)
        pl = (price - entry_price) * qty
        time_held = (time.time() - last_trade_time.get(symbol, time.time())) / 60
        message = (
            f"✅ SELL {symbol} qty:{qty} @ {price:.4f} ({reason})\n"
            f"🔸 Position Size: ${qty * price:.2f} | P/L: ${pl:.2f}\n"
            f"🔸 Time Held: {time_held:.0f}min\n"
            f"🔸 Order Status: {fill_status}\n"
            f"🔸 Daily Loss: ${daily_loss['loss']:.2f} | Remaining: ${(config.max_daily_loss_percent / 100 * daily_loss['starting_balance']) - daily_loss['loss']:.2f}"
        )
        notify(message)
        logger.info(message)
        open_positions.pop(symbol, None)
        save_state()
    except Exception as e:
        notify(f"🚫 close_position {symbol}: {e}")
        logger.error(f"close_position {symbol}: {e}")

def manage_position(symbol):
    if symbol not in open_positions:
        return
    tk = safe_fetch_ticker(symbol)
    if not tk:
        logger.warning(f"No ticker data for {symbol} in manage_position")
        return
    df15 = safe_fetch_ohlcv(symbol, '15m')
    if df15 is None or df15.empty or len(df15) < 20:
        logger.warning(f"Insufficient OHLCV data for {symbol} in manage_position")
        return
    rsi15 = get_rsi(df15['close']).iloc[-1]
    macd = df15['macd'].iloc[-1]
    signal_macd = df15['signal'].iloc[-1]
    atr = ta.volatility.AverageTrueRange(
        high=df15['high'], low=df15['low'], close=df15['close'], window=14
    ).average_true_range().iloc[-1]
    current_price = tk['last']
    pos = open_positions[symbol]
    pos['highest_price'] = max(pos['highest_price'], current_price)
    time_held = (time.time() - last_trade_time.get(symbol, time.time())) / 60
    df1h = safe_fetch_ohlcv(symbol, '1h')
    sma_1h = get_sma(df1h['close'], config.sma_period).iloc[-1] if df1h is not None else 0
    trend = "Below SMA" if current_price < sma_1h else "Above SMA" if sma_1h > 0 else "Unknown"
    atr_stop_loss = pos['entry_price'] - (atr * config.stop_loss_atr_multiplier)
    if current_price <= atr_stop_loss:
        loss = (pos['entry_price'] - current_price) * pos['qty']
        global daily_loss
        daily_loss['loss'] += loss
        save_daily_loss()
        close_position(symbol, pos['qty'], current_price, f"ATR Stop-loss | SMA Trend: {trend}")
        return
    trailing_threshold = pos['highest_price'] - (atr * config.trailing_atr_multiplier)
    if current_price <= trailing_threshold:
        profit_loss = (current_price - pos['entry_price']) * pos['qty']
        daily_loss['loss'] -= profit_loss
        save_daily_loss()
        close_position(symbol, pos['qty'], current_price, f"ATR Trailing stop | SMA Trend: {trend}")
        return
    for i, tp in enumerate(pos['tp_prices']):
        if current_price >= tp and tp not in pos['tps_triggered']:
            if rsi15 > 50 and macd < signal_macd:
                qty_to_sell = pos['qty'] * (0.5 if i < len(pos['tp_prices']) - 1 else 1.0)
                if qty_to_sell > 0:
                    profit = (current_price - pos['entry_price']) * qty_to_sell
                    daily_loss['loss'] -= profit
                    save_daily_loss()
                    close_position(symbol, qty_to_sell, current_price, f"TP {i+1} (ATR x {config.tp_multipliers[i]}) | SMA Trend: {trend}")
                    pos['tps_triggered'].append(tp)
                    pos['qty'] -= qty_to_sell
                    if pos['qty'] <= 0:
                        open_positions.pop(symbol, None)
                    save_state()
                    return
            else:
                reason = "RSI ≤ 50" if rsi15 <= 50 else "MACD Bullish"
                notify(f"🚫 TP {i+1} Skipped for {symbol}: {reason} | RSI: {rsi15:.2f} | MACD: {macd:.4f}/{signal:.4f}")
                logger.info(f"TP {i+1} Skipped for {symbol}: {reason}")
    adaptive_rsi_sell = get_adaptive_rsi_sell(
        df15, base=config.rsi_sell_base, multiplier=config.rsi_atr_multiplier,
        min_rsi=config.rsi_sell_min, max_rsi=config.rsi_sell_max
    )
    if rsi15 >= adaptive_rsi_sell:
        profit_loss = (current_price - pos['entry_price']) * pos['qty']
        daily_loss['loss'] -= profit_loss
        save_daily_loss()
        close_position(symbol, pos['qty'], current_price, f"RSI sell {rsi15:.2f} ≥ Adaptive {adaptive_rsi_sell} | SMA Trend: {trend}")
        return


def panic_close_all_positions():
    from utils.telegram import notify
    for symbol, pos in list(open_positions.items()):
        try:
            qty = pos.get('qty')
            price = pos.get('entry_price')
            if qty and qty > 0:
                close_position(symbol, qty, price, "🚨 PANIC CLOSE via Telegram")
                time.sleep(1)
        except Exception as e:
            notify(f"⚠️ Failed to close {symbol}: {e}")


def cancel_all_orders():
    from utils.telegram import notify
    try:
        mk = exchange.load_markets()
        symbols = config.symbols  # You already have this defined in your config

        for symbol in symbols:
            try:
                orders = exchange.fetch_open_orders(symbol)
                for order in orders:
                    exchange.cancel_order(order['id'], symbol)
                    logger.info(f"Cancelled order {order['id']} for {symbol}")
            except Exception as sym_err:
                logger.warning(f"⚠️ Could not fetch/cancel orders for {symbol}: {sym_err}")
        
        notify("✅ All pending orders cancelled via Telegram.")
        
    except Exception as e:
        logger.error(f"cancel_all_orders failed: {e}")
        notify(f"⚠️ Failed to cancel orders: {e}")




def trade(symbol, df15, df1h, prec):
    if len(open_positions) >= config.max_concurrent_trades:
        logger.info(f"Max concurrent trades reached ({config.max_concurrent_trades}), skipping {symbol}")
        return

    if not can_trade_now(symbol):
        logger.info(f"Cooldown active for {symbol}, skipping trade")
        return

    bal = safe_fetch_balance()
    usdt = bal['free'].get('USDT', 0)
    if usdt < config.minimum_balance:
        logger.info(f"Insufficient USDT balance {usdt:.4f}, skipping {symbol}")
        return

    global daily_loss
    if daily_loss['loss'] / daily_loss['starting_balance'] >= config.max_daily_loss_percent / 100:
        logger.info(f"Daily loss limit reached, skipping {symbol}")
        notify(f"🚫 Daily loss limit reached for {symbol} | Daily Loss: ${daily_loss['loss']:.2f}")
        return

    # === Budget Calculation ===
    budget = max(min(usdt * config.percent_per_trade, config.max_trade_usdt), config.min_trade_usdt)

    # === Indicators ===
    current_rsi_15m = df15['rsi'].iloc[-1]
    current_rsi_1h = df1h['rsi'].iloc[-1]
    macd_15m = df15['macd_hist'].iloc[-1]
    macd_1h = df1h['macd_hist'].iloc[-1]
    price = df15['close'].iloc[-1]
    lower_bb_15m = df15['lower_band'].iloc[-1]
    sma_1h = df1h['sma'].iloc[-1]
    atr = ta.volatility.AverageTrueRange(
        high=df15['high'], low=df15['low'], close=df15['close'], window=config.atr_period
    ).average_true_range().iloc[-1]
    hammer = is_hammer_candle(df15)
    trend = "Below SMA" if price < sma_1h else "Above SMA"

    logger.info(
        f"[DEBUG] {symbol} RSI(15m): {current_rsi_15m:.2f}, MACD(15m): {macd_15m:.4f}, "
        f"Price: {price:.4f}, Lower BB: {lower_bb_15m:.4f}, SMA(1h): {sma_1h:.4f}, ATR: {atr:.4f}"
    )

    from utils.entry_conditions import evaluate_all_entry_conditions
    passed, strategy, explanation = evaluate_all_entry_conditions(df15, df1h, config)

    if not passed:
        now = time.time()
        if now - no_entry_alerts_sent.get(symbol, 0) > 120:
            log_missed_trade_conditions(symbol, df15, explanation, df1h)
            no_entry_alerts_sent[symbol] = now
        return

    logger.info(f"✅ Entry Logic Passed: {strategy} | {explanation}")
    adaptive_rsi_levels = get_adaptive_rsi_levels(df15, config.rsi_entry_zones,
                                                  atr_multiplier=config.rsi_atr_multiplier,
                                                  atr_period=config.atr_period)

    confirmed = current_rsi_1h < config.rsi_1h_max

    for lvl in adaptive_rsi_levels:
        key = f"{symbol}_{lvl}"
        if rsi_alerts_sent.get(key):
            continue
        if confirmed and abs(current_rsi_15m - lvl) <= config.rsi_tolerance:
            qty = round(budget / price, prec)
            if qty <= 0:
                logger.info(f"Quantity {qty} too low for {symbol}, skipping")
                continue

            try:
                ticker = safe_fetch_ticker(symbol)
                if not ticker:
                    logger.error(f"No ticker data for {symbol}, skipping")
                    continue

                limit_price = ticker['ask'] * (1 + config.limit_order_offset)
                order = exchange.create_limit_buy_order(symbol, qty, limit_price)
                time.sleep(1.5)
                oi = exchange.fetch_order(order['id'], symbol)
                fill_status = f"{oi['filled'] / qty * 100:.0f}%" if oi.get('filled') else "Unknown"

                if oi['status'] == 'closed' and oi['filled'] >= qty * 0.99:
                    open_positions[symbol] = {
                        'entry_price': oi.get('average', price),
                        'qty': oi['filled'],
                        'highest_price': price,
                        'tps_triggered': [],
                        'tp_prices': [],
                        'atr': atr
                    }
                    set_take_profit(symbol, open_positions[symbol], exchange, logger)
                    rsi_alerts_sent[key] = True
                    last_trade_time[symbol] = time.time()
                    save_state()

                    avg_volume = df15['volume'].rolling(window=config.volume_lookback).mean().iloc[-1]
                    tp_prices = [open_positions[symbol]['entry_price'] + (atr * mult) for mult in config.tp_multipliers]

                    message = (
                        f"📈 Entry Signal: {symbol} @ RSI ≈ {lvl} (±{config.rsi_tolerance}){' with Hammer' if hammer else ''}\n"
                        f"💡 Strategy: {strategy}\n"
                        f"💰 Price: {oi.get('average', price):.4f} | Limit Order\n"
                        f"📊 RSI(15m): {current_rsi_15m:.2f} | RSI(1h): {current_rsi_1h:.2f}\n"
                        f"📊 MACD(15m): {macd_15m:.4f} | MACD(1h): {macd_1h:.4f}\n"
                        f"📊 Bollinger: Lower BB: {lower_bb_15m:.4f} | Price: {price:.4f}\n"
                        f"📊 Volume: {df15['volume'].iloc[-1]:.0f} ≥ Avg: {avg_volume:.0f}\n"
                        f"📊 SMA Trend: {trend}\n"
                        f"📊 ATR: {atr:.4f}\n"
                        f"🎯 TPs: {', '.join([f'${p:.4f}' for p in tp_prices])}\n"
                        f"🧮 Position Size: ${qty * price:.2f}\n"
                        f"✅ Entry Confirmed!"
                    )

                    notify(message)
                    logger.info(message)
                    return
                else:
                    logger.warning(f"Order not filled for {symbol}: Status {oi.get('status')}, Filled: {oi.get('filled')}/{qty}")
                    notify(f"🚫 Order not filled for {symbol}. Status: {oi.get('status')} | Fill: {fill_status}")
            except Exception as e:
                logger.error(f"Trade error for {symbol}: {e}")
                notify(f"❌ Trade error for {symbol}: {e}")
                return
        else:
            now = time.time()
            if now - no_entry_alerts_sent.get(symbol, 0) > 120:
                log_missed_trade_conditions(symbol, df15, f"Not within RSI tolerance ({lvl})", df1h)
                no_entry_alerts_sent[symbol] = now





def trade_loop():
    consecutive_fetch_errors = 0
    FETCH_ERROR_THRESHOLD = 3

    while True:
        # ✅ Telegram Pause Check (stop/resume)
        if not is_bot_active["status"]:
            logger.info("⏸️ Bot is currently stopped via Telegram.")
            time.sleep(5)
            continue

        syms = config.symbols

        # 🔍 Volatility Scanner
        if getattr(config, 'enable_volatility_scan', False):
            try:
                volatile = get_top_volatile_tokens(exchange, **config.volatility_filters)
                syms = [sym for sym, _, _ in volatile if sym not in open_positions]

                for sym, pct, vol in volatile:
                    notify(f"🔥 Volatile Token Detected: {sym} | {pct:.2f}% | Vol ${vol:,.0f}")
                    logger.info(f"🔥 Volatile Token: {sym} | Change: {pct:.2f}% | Vol: ${vol:,.0f}")

            except Exception as e:
                logger.warning(f"⚠️ Volatility scan failed: {e}")
                syms = config.symbols

        ohlcv_cache = {}

        for sym in syms:
            try:
                if not is_bot_active["status"]:
                    logger.info("⏸️ Bot paused mid-scan. Exiting current loop early.")
                    break

                if sym not in ohlcv_cache:
                    ohlcv_cache[sym] = {}

                # 15m Data
                if '15m' not in ohlcv_cache[sym]:
                    df15 = safe_fetch_ohlcv(sym, '15m')
                    if df15 is not None and not df15.empty:
                        df15, ok15 = prepare_indicators(df15)
                        if ok15:
                            df15['rsi'] = get_rsi(df15['close'])
                            df15['macd'], df15['signal'], df15['macd_hist'] = get_macd(df15['close'])
                            df15['upper_band'], df15['middle_band'], df15['lower_band'] = get_bollinger_bands(df15['close'])
                            ohlcv_cache[sym]['15m'] = df15
                    time.sleep(0.5)
                else:
                    df15 = ohlcv_cache[sym]['15m']

                # 1h Data
                if '1h' not in ohlcv_cache[sym]:
                    df1h = safe_fetch_ohlcv(sym, '1h')
                    if df1h is not None and not df1h.empty:
                        df1h, ok1h = prepare_indicators(df1h)
                        if ok1h:
                            df1h['rsi'] = get_rsi(df1h['close'])
                            df1h['macd'], df1h['signal'], df1h['macd_hist'] = get_macd(df1h['close'])
                            df1h['sma'] = get_sma(df1h['close'], config.sma_period)
                            ohlcv_cache[sym]['1h'] = df1h
                    time.sleep(0.5)
                else:
                    df1h = ohlcv_cache[sym]['1h']

                # Handle missing data
                if df15 is None or df1h is None:
                    consecutive_fetch_errors += 1
                    logger.warning(f"⚠️ OHLCV fetch None for {sym}. Errors: {consecutive_fetch_errors}")
                    if consecutive_fetch_errors >= FETCH_ERROR_THRESHOLD:
                        logger.warning("🚨 Too many fetch errors, sleeping for 60s")
                        time.sleep(60)
                        consecutive_fetch_errors = 0
                    continue
                else:
                    consecutive_fetch_errors = 0

                if df15.get('rsi') is None or df1h.get('rsi') is None:
                    logger.warning(f"⚠️ {sym}: Indicators not ready, skipping")
                    continue

                mk = exchange.load_markets()
                prec = mk[sym]['precision']['amount']

                # Manage position
                manage_position(sym)
                trade(sym, df15, df1h, prec)

            except Exception as e:
                logger.error(f"⚠️ Error processing {sym}: {e}")

        time.sleep(60)



def validate_api_keys():
    try:
        bal = exchange.fetch_balance()
        notify(f"✅ API OK. USDT: ${bal['free'].get('USDT',0):.2f}")
    except Exception as e:
        notify(f"❌ API error: {e}")
        exit(1)

def hard_stop_loss_loop():
    while True:
        sync_positions()
        time.sleep(1.2)

# main.py



markets = None
volume_lookback = None
daily_loss = None

from utils.telegram_command_poll import telegram_command_loop, is_bot_active

def main():
    global markets, volume_lookback, daily_loss
    validate_api_keys()
    markets = exchange.load_markets()
    volume_lookback = int(getattr(config, 'volume_lookback', 10))
    daily_loss = load_daily_loss()


    # 🔔 Notify Telegram on startup if paused
    if not is_bot_active["status"]:
        notify("⏸️ Bot is paused. Send /start to start trading.")


    threading.Thread(target=hard_stop_loss_loop, daemon=True).start()
    threading.Thread(target=telegram_command_loop, daemon=True).start()
    
    trade_loop()


if __name__ == "__main__":
    main()

__all__ = ["panic_close_all_positions", "cancel_all_orders"]

