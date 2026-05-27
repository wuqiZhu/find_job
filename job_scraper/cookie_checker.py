"""Cookie 健康检查模块

检查各平台 Cookie 是否有效，过期时发送钉钉通知提醒更新。

使用方式：
    python -m job_scraper.cookie_checker          # 检查所有 Cookie
    python -m job_scraper.cookie_checker --boss    # 只检查 Boss 直聘
    python -m job_scraper.cookie_checker --notify  # 检查并发送通知
"""

import os
import sys
import json
import time
import hashlib
import hmac
import base64
import urllib.parse
import logging
import argparse
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def load_env():
    """加载 .env 文件"""
    env_path = Path(__file__).parent.parent / '.env'
    if not env_path.exists():
        return
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                if key and key not in os.environ:
                    os.environ[key] = value


def check_boss_cookie() -> dict:
    """检查 Boss 直聘 Cookie"""
    cookie = os.environ.get('BOSS_COOKIE', '')
    if not cookie:
        return {"platform": "Boss直聘", "status": "missing", "message": "Cookie 未配置"}

    try:
        import urllib.request
        req = urllib.request.Request(
            "https://www.zhipin.com/wapi/zpgeek/search/joblist.json?query=Python&city=100010000&page=1&pageSize=1",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Cookie": cookie,
                "Referer": "https://www.zhipin.com/",
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('code') == 0:
                return {"platform": "Boss直聘", "status": "valid", "message": "Cookie 有效"}
            elif data.get('code') == 1:
                return {"platform": "Boss直聘", "status": "expired", "message": f"Cookie 已过期: {data.get('message', '未知错误')}"}
            else:
                return {"platform": "Boss直聘", "status": "unknown", "message": f"未知状态: code={data.get('code')}, message={data.get('message', '')}"}
    except Exception as e:
        return {"platform": "Boss直聘", "status": "error", "message": f"检查失败: {str(e)}"}


def check_zhaopin_cookie() -> dict:
    """检查智联招聘 Cookie"""
    cookie = os.environ.get('ZHAOPIN_COOKIE', '')
    at = os.environ.get('ZHAOPIN_AT', '')
    rt = os.environ.get('ZHAOPIN_RT', '')

    if not cookie and not at:
        return {"platform": "智联招聘", "status": "missing", "message": "Cookie 未配置"}

    if not at:
        return {"platform": "智联招聘", "status": "incomplete", "message": "ZHAOPIN_AT 未配置（需要 access token）"}

    try:
        import urllib.request
        req = urllib.request.Request(
            "https://fe-api.zhaopin.com/c/i/sou?pageSize=1&cityId=530&kw=Python",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "x-access-token": at,
                "Referer": "https://sou.zhaopin.com/",
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('code') == 200:
                return {"platform": "智联招聘", "status": "valid", "message": "Token 有效"}
            else:
                return {"platform": "智联招聘", "status": "expired", "message": f"Token 可能已过期: code={data.get('code')}"}
    except Exception as e:
        return {"platform": "智联招聘", "status": "error", "message": f"检查失败: {str(e)}"}


def check_liepin_cookie() -> dict:
    """检查猎聘 Cookie"""
    cookie = os.environ.get('LIEPIN_COOKIE', '')
    if not cookie:
        return {"platform": "猎聘", "status": "missing", "message": "Cookie 未配置"}

    try:
        import urllib.request
        req = urllib.request.Request(
            "https://www.liepin.com/api/com.liepin.searchfront4c.pc-search-job?key=Python&curPage=0&pageSize=1",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Cookie": cookie,
                "Referer": "https://www.liepin.com/",
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('code') == 0:
                return {"platform": "猎聘", "status": "valid", "message": "Cookie 有效"}
            else:
                return {"platform": "猎聘", "status": "expired", "message": f"Cookie 可能已过期: code={data.get('code')}"}
    except Exception as e:
        return {"platform": "猎聘", "status": "error", "message": f"检查失败: {str(e)}"}


def check_all_cookies() -> list:
    """检查所有平台 Cookie"""
    results = []
    results.append(check_boss_cookie())
    results.append(check_zhaopin_cookie())
    results.append(check_liepin_cookie())
    return results


def send_dingtalk_notification(results: list):
    """发送钉钉通知"""
    webhook = os.environ.get('DINGTALK_WEBHOOK', '')
    secret = os.environ.get('DINGTALK_SECRET', '')

    if not webhook:
        logger.warning("DINGTALK_WEBHOOK 未配置，跳过通知")
        return

    expired = [r for r in results if r['status'] in ('expired', 'missing', 'incomplete')]
    if not expired:
        return

    lines = ["## ⚠️ Cookie 健康检查报告", ""]
    for r in results:
        icon = {"valid": "✅", "expired": "❌", "missing": "⚪", "incomplete": "⚠️", "error": "🔴"}.get(r['status'], "❓")
        lines.append(f"- {icon} **{r['platform']}**: {r['message']}")

    lines.append("")
    lines.append(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("请尽快更新过期的 Cookie，否则对应平台的岗位抓取将失败。")

    text = "\n".join(lines)

    # 确保消息正文包含关键词"通知"（钉钉机器人安全设置要求）
    if "通知" not in text:
        text = f"**通知**\n\n{text}"

    try:
        import urllib.request
        if secret:
            timestamp = str(round(time.time() * 1000))
            string_to_sign = f"{timestamp}\n{secret}"
            hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
            sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
            url = f"{webhook}&timestamp={timestamp}&sign={sign}"
        else:
            url = webhook

        payload = json.dumps({
            "msgtype": "markdown",
            "markdown": {
                "title": "Cookie 健康检查",
                "text": text
            }
        }).encode('utf-8')

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            if result.get('errcode') == 0:
                logger.info("钉钉通知发送成功")
            else:
                logger.error(f"钉钉通知发送失败: {result}")
    except Exception as e:
        logger.error(f"钉钉通知发送异常: {e}")


def main():
    parser = argparse.ArgumentParser(description="Cookie 健康检查")
    parser.add_argument("--boss", action="store_true", help="只检查 Boss 直聘")
    parser.add_argument("--zhaopin", action="store_true", help="只检查智联招聘")
    parser.add_argument("--liepin", action="store_true", help="只检查猎聘")
    parser.add_argument("--notify", action="store_true", help="检查后发送钉钉通知")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    load_env()

    if args.boss:
        results = [check_boss_cookie()]
    elif args.zhaopin:
        results = [check_zhaopin_cookie()]
    elif args.liepin:
        results = [check_liepin_cookie()]
    else:
        results = check_all_cookies()

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print("\n=== Cookie 健康检查 ===\n")
        for r in results:
            icon = {"valid": "✅", "expired": "❌", "missing": "⚪", "incomplete": "⚠️", "error": "🔴"}.get(r['status'], "❓")
            print(f"  {icon} {r['platform']}: {r['message']}")
        print()

    if args.notify:
        send_dingtalk_notification(results)

    has_issue = any(r['status'] in ('expired', 'missing', 'incomplete') for r in results)
    return 0 if not has_issue else 1


if __name__ == '__main__':
    sys.exit(main())
