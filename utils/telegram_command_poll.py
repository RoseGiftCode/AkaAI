# ✅ utils/telegram_command_poll.py

import requests
import time
import config
import fcntl
from utils.bot_state import is_bot_active

# Prevent multiple pollers running simultaneously (Linux-specific)
lockfile = open("/tmp/telegram_poll.lock", "w")
try:
    fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
except IOError:
    print("Another instance of Telegram polling is already running.")
    exit(1)

# ✅ Thread-safe mutable holder for last update ID
_last_update_id_holder = {"value": None}

def send_msg(msg):
    if config.use_telegram:
        try:
            url = f"https://api.telegram.org/bot{config.telegram_token}/sendMessage"
            data = {"chat_id": config.telegram_chat_id, "text": msg}
            requests.post(url, data=data)
        except Exception as e:
            print("Telegram send error:", e)

def check_telegram_commands():
    from bot import panic_close_all_positions, cancel_all_orders
    from utils.portfolio import (
        show_balance, show_portfolio, show_pnl, show_fees, show_max_drawdown,
        show_open_positions, show_position_details, show_pending_orders,
        show_orderbook_snapshot, recommend_symbol, show_last_entry,
        show_last_close, manual_buy, manual_sell, manual_cancel,
        trigger_take_profit, trigger_stop_loss, get_scanner_results
    )

    url = f"https://api.telegram.org/bot{config.telegram_token}/getUpdates"

    try:
        params = {"timeout": 10}
        if _last_update_id_holder["value"]:
            params["offset"] = _last_update_id_holder["value"] + 1

        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()

        if not data.get("ok"):
            print("⚠️ Telegram polling failed:", data)
            return

        for update in data.get("result", []):
            _last_update_id_holder["value"] = update["update_id"]
            message = update.get("message", {})
            if not message or "text" not in message:
                continue

            text = message.get("text", "")
            chat_id = str(message.get("chat", {}).get("id"))

            print(f"📩 Received message: {text} from chat ID: {chat_id}")

            if chat_id not in map(str, config.telegram_allowed_users):
                print("⛔ Unauthorized user.")
                continue

            cmd = text.strip().lower()
            parts = cmd.split()

            # 🔧 BOT CONTROLS
            if cmd == "/start":
                is_bot_active["status"] = True
                send_msg("✅ Bot STARTED. GET RICH 💵")
            elif cmd == "/stop":
                is_bot_active["status"] = False
                send_msg("⛔ Bot STOPPED.")
            elif cmd == "/status":
                status_msg = "🟢 Bot is RUNNING.GET RICH 💵" if is_bot_active["status"] else "🔴 Bot is STOPPED."
                send_msg(status_msg)
            elif cmd == "/panicclose":
                send_msg("⚠️ Closing all open positions...")
                panic_close_all_positions()
            elif cmd == "/cancelall":
                send_msg("⚠️ Cancelling all open orders...")
                cancel_all_orders()
            elif cmd == "/restart":
                send_msg("♻️ Restarting bot (soft reload)...")
                import os
                os.execlp("python", "python", "main.py")
            elif cmd == "/rebootserver":
                send_msg("🔁 Rebooting server...")
                import os
                os.system("reboot")

            # 📊 REPORTING
            elif cmd in ["/balance", "/b"]:
                send_msg(show_balance())
            elif cmd == "/portfolio":
                send_msg(show_portfolio())
            elif cmd == "/pnl":
                send_msg(show_pnl())
            elif cmd == "/fees":
                send_msg(show_fees())
            elif cmd == "/maxdrawdown":
                send_msg(show_max_drawdown())
            elif cmd == "/openpositions":
                send_msg(show_open_positions())
            elif cmd.startswith("/position") and len(parts) == 2:
                send_msg(show_position_details(parts[1].upper()))
            elif cmd == "/orders":
                send_msg(show_pending_orders())
            elif cmd.startswith("/orderbook") and len(parts) == 2:
                send_msg(show_orderbook_snapshot(parts[1].upper()))
            elif cmd.startswith("/recommend") and len(parts) == 2:
                send_msg(recommend_symbol(parts[1].upper()))
            elif cmd == "/lastentry":
                send_msg(show_last_entry())
            elif cmd == "/lastclose":
                send_msg(show_last_close())

            # 🛠️ MANUAL TRADING
            elif cmd.startswith("/buy") and len(parts) == 3:
                try:
                    amount = float(parts[2])
                    send_msg(manual_buy(parts[1].upper(), amount))
                except ValueError:
                    send_msg("❌ Invalid amount format.")
            elif cmd.startswith("/sell") and len(parts) == 2:
                send_msg(manual_sell(parts[1].upper()))
            elif cmd.startswith("/cancel") and len(parts) == 2:
                send_msg(manual_cancel(parts[1].upper()))
            elif cmd.startswith("/takeprofit") and len(parts) == 2:
                send_msg(trigger_take_profit(parts[1].upper()))
            elif cmd.startswith("/stoploss") and len(parts) == 2:
                send_msg(trigger_stop_loss(parts[1].upper()))
            elif cmd == "/scanner":
                send_msg(get_scanner_results())

            # 📘 HELP
            elif cmd == "/help":
                help_text = """📘 Available Commands:
/start, /stop, /status
/panicclose, /cancelall, /restart
/balance, /portfolio, /pnl, /fees, /maxdrawdown
/openpositions, /position <symbol>, /orders
/orderbook <symbol>, /scanner, /recommend <symbol>
/lastentry, /lastclose
/buy <symbol> <amount>, /sell <symbol>, /cancel <symbol>
/takeprofit <symbol>, /stoploss <symbol>"""
                send_msg(help_text)

    except Exception as e:
        print("Telegram command check failed:", e)

def telegram_command_loop():
    while True:
        check_telegram_commands()
        time.sleep(getattr(config, "telegram_poll_delay", 5))  # Default to 5s if not set
