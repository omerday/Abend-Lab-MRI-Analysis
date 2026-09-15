#!/usr/bin/env python3
"""
Standalone Telegram Notification Helper for Abend Lab MRI Pipeline.
Allows manual terminal scripts or cronjobs to push notifications directly to Telegram.
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.parse
from typing import Optional, List
from .config import config

def send_telegram_message(
    message: str,
    bot_token: Optional[str] = None,
    chat_ids: Optional[List[int]] = None,
    parse_mode: str = "Markdown",
) -> bool:
    """Send a text message to authorized Telegram chats using standard urllib."""
    token = bot_token or config.bot_token
    recipients = chat_ids or config.allowed_user_ids

    if not token or not recipients:
        print("[Error] Missing Telegram bot token or recipient chat IDs.", file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    success = True

    for chat_id in recipients:
        data = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": parse_mode,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status != 200:
                    success = False
        except Exception as e:
            print(f"[Error sending message to {chat_id}]: {e}", file=sys.stderr)
            success = False

    return success

def send_telegram_photo(
    photo_path: str,
    caption: str = "",
    bot_token: Optional[str] = None,
    chat_ids: Optional[List[int]] = None,
) -> bool:
    """Send a photo to authorized Telegram chats using multipart form data."""
    token = bot_token or config.bot_token
    recipients = chat_ids or config.allowed_user_ids

    if not token or not recipients or not os.path.exists(photo_path):
        return False

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    
    with open(photo_path, "rb") as f:
        photo_bytes = f.read()

    filename = os.path.basename(photo_path)
    body = bytearray()
    body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n".encode("utf-8"))
    body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"{filename}\"\r\nContent-Type: image/png\r\n\r\n".encode("utf-8"))
    body.extend(photo_bytes)
    body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    success = True
    for chat_id in recipients:
        per_user_body = bytearray()
        per_user_body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n".encode("utf-8"))
        per_user_body.extend(body)

        req = urllib.request.Request(
            url,
            data=per_user_body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status != 200:
                    success = False
        except Exception as e:
            print(f"[Error sending photo to {chat_id}]: {e}", file=sys.stderr)
            success = False

    return success

def main():
    parser = argparse.ArgumentParser(description="Send notifications to Telegram from scripts or terminal.")
    parser.add_argument("--message", "-m", required=True, help="Message text to send (supports Markdown).")
    parser.add_argument("--photo", "-p", help="Path to an image file (e.g. Chauffeur PNG).")
    args = parser.parse_args()

    if args.photo and os.path.exists(args.photo):
        ok = send_telegram_photo(args.photo, caption=args.message)
    else:
        ok = send_telegram_message(args.message)

    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
