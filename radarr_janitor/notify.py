from __future__ import annotations

import requests


def send_telegram(bot_token: str, chat_id: str, text: str) -> bool:
    """Fire a Telegram message via the Bot API. Returns True on success.

    Works from headless cron (plain HTTPS, no MCP needed).
    """
    if not bot_token or not chat_id:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True},
            timeout=20,
        )
        return r.status_code == 200
    except requests.RequestException:
        return False
