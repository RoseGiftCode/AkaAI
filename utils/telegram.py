from config import use_telegram, telegram_token, telegram_chat_id
import requests

def notify(msg):
    if use_telegram:
        url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        data = {"chat_id": telegram_chat_id, "text": msg}
        try:
            requests.post(url, data=data)
        except Exception as e:
            print("Telegram error:", e)
