#!/usr/bin/env python3
"""
Standalone Telegram Notification Helper for Abend Lab MRI Pipeline.
Allows manual terminal scripts, pipelines, or cronjobs to push notifications
directly to Telegram with robust Markdown/HTML formatting and error resilience.
"""

import argparse
import html
import json
import logging
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, List, Optional, Tuple

from .config import config

logger = logging.getLogger("remote_monitor.notify")


def escape_markdown(text: str) -> str:
    """
    Escape Telegram Markdown V1 special characters, particularly underscores
    in AFNI filenames (e.g. sub-435_pain_by_rating_stats).

    Parameters
    ----------
    text : str
        Raw input string.

    Returns
    -------
    str
        Escaped string safe for Telegram Markdown V1 formatting.
    """
    if not text:
        return ""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


def escape_html(text: Any) -> str:
    """
    Escape HTML special characters for safe Telegram HTML formatting.

    Parameters
    ----------
    text : Any
        Raw input value.

    Returns
    -------
    str
        Escaped HTML string.
    """
    return html.escape(str(text)) if text is not None else ""


def _post_json(url: str, payload: dict, timeout: int = 10) -> Tuple[bool, Optional[int]]:
    """Helper to post JSON data using standard urllib with status tracking."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status == 200, response.status
    except urllib.error.HTTPError as e:
        return False, e.code
    except Exception as e:
        logger.error("Network request failed: %s", e)
        return False, None


def send_telegram_message(
    message: str,
    bot_token: Optional[str] = None,
    chat_ids: Optional[List[int]] = None,
    parse_mode: Optional[str] = "HTML",
) -> bool:
    """
    Send a text message to authorized Telegram chats using standard urllib.

    Automatically handles underscore escaping for Markdown V1 and provides
    plain-text fallback if Telegram entity parsing fails.

    Parameters
    ----------
    message : str
        Message content to send.
    bot_token : Optional[str]
        Telegram bot API token (defaults to config.bot_token).
    chat_ids : Optional[List[int]]
        List of recipient Telegram chat IDs (defaults to config.allowed_user_ids).
    parse_mode : Optional[str]
        Formatting mode: 'HTML', 'Markdown', 'MarkdownV2', or None. Default 'HTML'.

    Returns
    -------
    bool
        True if the message was delivered to all recipients, False otherwise.
    """
    token = bot_token or config.bot_token
    recipients = chat_ids or config.allowed_user_ids

    if not token or not recipients:
        logger.error("Missing Telegram bot token or recipient chat IDs.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    success = True

    # Sanitize message if using Markdown V1 to prevent parse errors on AFNI underscores
    send_text = message
    if parse_mode == "Markdown":
        send_text = re.sub(r"(?<!\\)_", r"\_", message)

    for chat_id in recipients:
        payload = {
            "chat_id": chat_id,
            "text": send_text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        ok, status_code = _post_json(url, payload)

        # If HTTP 400 Bad Request (commonly an entity parsing failure), retry as plain text
        if not ok and status_code == 400 and parse_mode:
            logger.warning(
                "Telegram entity parse failed with parse_mode=%s for chat %s. Retrying as plain text.",
                parse_mode,
                chat_id,
            )
            fallback_payload = {"chat_id": chat_id, "text": message}
            ok, _ = _post_json(url, fallback_payload)

        if not ok:
            logger.error("Failed to deliver message to chat %s (status=%s)", chat_id, status_code)
            success = False

    return success


def send_telegram_photo(
    photo_path: str,
    caption: str = "",
    bot_token: Optional[str] = None,
    chat_ids: Optional[List[int]] = None,
    parse_mode: Optional[str] = "HTML",
) -> bool:
    """
    Send a photo to authorized Telegram chats using multipart/form-data.

    Detects file MIME type dynamically and safely escapes captions.

    Parameters
    ----------
    photo_path : str
        Filesystem path to the image file.
    caption : str
        Optional photo caption text.
    bot_token : Optional[str]
        Telegram bot API token.
    chat_ids : Optional[List[int]]
        List of recipient Telegram chat IDs.
    parse_mode : Optional[str]
        Formatting mode for caption ('HTML', 'Markdown', or None).

    Returns
    -------
    bool
        True if the photo was delivered to all recipients, False otherwise.
    """
    token = bot_token or config.bot_token
    recipients = chat_ids or config.allowed_user_ids

    if not token or not recipients or not os.path.exists(photo_path):
        logger.error("Cannot send photo: invalid token, recipients, or file not found (%s)", photo_path)
        return False

    mime_type, _ = mimetypes.guess_type(photo_path)
    if not mime_type:
        mime_type = "image/png"

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"

    try:
        with open(photo_path, "rb") as f:
            photo_bytes = f.read()
    except OSError as e:
        logger.error("Failed to read photo file %s: %s", photo_path, e)
        return False

    filename = os.path.basename(photo_path)

    # Sanitize caption if using Markdown
    send_caption = caption
    if parse_mode == "Markdown" and caption:
        send_caption = re.sub(r"(?<!\\)_", r"\_", caption)

    body = bytearray()
    if send_caption:
        body.extend(
            f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{send_caption}\r\n'.encode("utf-8")
        )
        if parse_mode:
            body.extend(
                f'--{boundary}\r\nContent-Disposition: form-data; name="parse_mode"\r\n\r\n{parse_mode}\r\n'.encode(
                    "utf-8"
                )
            )

    body.extend(
        f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="{filename}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8")
    )
    body.extend(photo_bytes)
    body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    success = True
    for chat_id in recipients:
        per_user_body = bytearray()
        per_user_body.extend(
            f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode("utf-8")
        )
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
        except urllib.error.HTTPError as e:
            # If parse error on caption, retry without caption parse_mode
            if e.code == 400 and parse_mode and caption:
                logger.warning("Photo caption parse failed for chat %s. Retrying without formatting.", chat_id)
                retry_body = bytearray()
                retry_body.extend(
                    f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode(
                        "utf-8"
                    )
                )
                retry_body.extend(
                    f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'.encode(
                        "utf-8"
                    )
                )
                retry_body.extend(
                    f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="{filename}"\r\n'
                    f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8")
                )
                retry_body.extend(photo_bytes)
                retry_body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))
                try:
                    retry_req = urllib.request.Request(
                        url,
                        data=retry_body,
                        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                    )
                    with urllib.request.urlopen(retry_req, timeout=15) as retry_resp:
                        if retry_resp.status != 200:
                            success = False
                except Exception as retry_e:
                    logger.error("Retry sending photo failed for %s: %s", chat_id, retry_e)
                    success = False
            else:
                logger.error("Error sending photo to %s: %s", chat_id, e)
                success = False
        except Exception as e:
            logger.error("Unexpected error sending photo to %s: %s", chat_id, e)
            success = False

    return success


def main():
    """Command line interface for dispatching notifications."""
    parser = argparse.ArgumentParser(description="Send notifications to Telegram from scripts or terminal.")
    parser.add_argument("--message", "-m", required=True, help="Message text to send.")
    parser.add_argument("--photo", "-p", help="Path to an image file (e.g. Chauffeur PNG).")
    parser.add_argument(
        "--parse-mode",
        choices=["HTML", "Markdown", "none"],
        default="HTML",
        help="Message parse mode (default: HTML).",
    )
    args = parser.parse_args()

    mode = None if args.parse_mode == "none" else args.parse_mode

    if args.photo and os.path.exists(args.photo):
        ok = send_telegram_photo(args.photo, caption=args.message, parse_mode=mode)
    else:
        ok = send_telegram_message(args.message, parse_mode=mode)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
