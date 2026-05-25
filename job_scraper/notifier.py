"""钉钉通知模块"""
import time
import hmac
import hashlib
import base64
import urllib.parse
import logging
from .config import get_config

logger = logging.getLogger(__name__)


def _get_webhook_url() -> str:
    config = get_config()
    webhook = config.get('dingtalk_webhook', '')
    if not webhook:
        return None

    secret = config.get('dingtalk_secret', '')
    if secret:
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(
            secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        separator = "&" if "?" in webhook else "?"
        webhook = f"{webhook}{separator}timestamp={timestamp}&sign={sign}"
    return webhook


def _post(payload: dict) -> bool:
    try:
        from curl_cffi import requests as curl_requests
        use_curl = True
    except ImportError:
        import requests as std_requests
        use_curl = False

    webhook_url = _get_webhook_url()
    if not webhook_url:
        logger.warning("DINGTALK_WEBHOOK 未设置，跳过通知")
        return False

    try:
        if use_curl:
            resp = curl_requests.post(webhook_url, json=payload, timeout=10)
        else:
            resp = std_requests.post(webhook_url, json=payload, timeout=10)
        result = resp.json()
        if result.get("errcode") == 0:
            logger.info("钉钉通知发送成功: %s", payload.get("actionCard", {}).get("title", payload.get("markdown", {}).get("title", "")))
            return True
        else:
            logger.error("钉钉通知失败: %s", result)
            return False
    except Exception as e:
        logger.error("钉钉通知异常: %s", e)
        return False


def send_markdown(title: str, content: str) -> bool:
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": content}
    }
    return _post(payload)


def send_actioncard(title: str, text: str, buttons: list) -> bool:
    payload = {
        "msgtype": "actionCard",
        "actionCard": {
            "title": title,
            "text": text,
            "btns": buttons
        }
    }
    return _post(payload)
