# config.py
import os

# === CAPITAL & RISK MANAGEMENT ===
budget_usdt = 160                  # Total account size to base allocations on
minimum_balance = 1                # Leave $1 as buffer to avoid over-trading or errors
percent_per_trade = 0.10           # Use up to 10% of available capital per trade
min_trade_usdt = 5                # Avoid micro trades that can get stuck or fail
max_trade_usdt = 10               # Prevent any single trade from using full balance
max_concurrent_trades = 1          # One trade at a time in volatility mode for better control

# === TRADE COOLDOWN & LIMITS ===
trade_cooldown_sec = 120           # Prevents re-entry too quickly
max_daily_loss_percent = 5         # Stop trading after 5% capital loss

# === SYMBOLS ===
symbols = ['XRP/USDT']             # Only used if volatility scan is disabled
timeframe = '15m'

# === VOLATILITY SCAN SETTINGS ===
enable_volatility_scan = True
volatility_mode = 'multi'
volatility_filters = {
    'interval': '15m',
    'top_n': 10,
    'min_volume': 500000,
    'min_change_percent': 1,
    'max_price': 5
    'scan_interval': 60  # seconds
}

# === STOP LOSS / TRAILING ===
stop_loss_atr_multiplier = 1.0
trailing_atr_multiplier = 1.0

# === TAKE-PROFIT STRATEGY ===
tp_multipliers = [2.0, 4.0, 6.0]
tp_reset_delay_sec = 60

# === RSI ENTRY STRATEGY ===
rsi_entry_zones = [55, 50, 45, 40, 35, 30]
rsi_tolerance = 5
rsi_1h_max = 70
rsi_atr_multiplier = 1.5  # ⬅️ Add this

# === RSI EXIT STRATEGY ===
rsi_sell = 70
rsi_sell_base = 70
rsi_atr_multiplier = 1.5
rsi_sell_max = 80
rsi_sell_min = 60

# === MOVING AVERAGE / TREND ===
sma_period = 50
atr_period = 14

# === BOLLINGER BANDS ===
bb_period = 20
bb_stddev = 2

# === VOLUME ===
volume_lookback = 20

# === ZIGZAG (Optional) ===
zigzag_depth = 12
zigzag_deviation = 5

# === TELEGRAM ===
use_telegram = True
telegram_token = os.getenv('telegram_token')
telegram_chat_id = os.getenv('telegram_chat_id')
telegram_poll_delay = 2  # ⬅️ Add this line
telegram_allowed_users = [os.getenv('telegram_chat_id')]  # Replace with your real Telegram user ID

# === EXCHANGE KEYS ===
mexc_api_key = os.getenv('mexc_api_key')
mexc_api_secret = os.getenv('mexc_api_secret')

# === STRATEGY TOGGLES ===
enable_advanced_entry_strategies = True     # Toggle for new strategies like MACD+RSI etc.
min_entry_signals_required = 2              # For the default strategy (how many indicators must pass)
entry_mode = 'adaptive'                     # Options: 'default', 'adaptive', 'conservative'

# Optional toggles for strategy-specific features
use_zigzag_filter = False                    # Use zigzag confirmation (if implemented)
use_god_candle_filter = False                # Use god candle as optional signal boost



