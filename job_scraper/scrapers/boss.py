"""Boss直聘抓取器"""
import json
import time
import random
import urllib.parse
import logging

from ..config import get_config
from .base import parse_cookie_to_list, create_chrome_options, safe_quit_driver, set_cookie_error, COOKIE_ERROR

logger = logging.getLogger(__name__)


def search_boss_jobs_browser(query: str, city: str, page: int = 1, page_size: int = 30) -> list:
    try:
        from DrissionPage import ChromiumPage
    except ImportError:
        logger.warning("DrissionPage 未安装，跳过浏览器模式")
        return None

    config = get_config()
    boss_cookie = config.get('boss_cookie', '')

    co = create_chrome_options()
    if co is None:
        return None

    driver = None
    try:
        driver = ChromiumPage(co)

        if boss_cookie:
            driver.get("https://www.zhipin.com")
            time.sleep(2)
            for c in parse_cookie_to_list(boss_cookie):
                try:
                    driver.set.cookies(c)
                except Exception:
                    pass
            time.sleep(1)

        url = f"https://www.zhipin.com/web/geek/job?query={urllib.parse.quote(query)}&city={city}&experience=104,105,106"
        driver.get(url)
        time.sleep(random.uniform(3, 6))

        if '安全验证' in driver.html or 'verify' in driver.url.lower():
            logger.warning("触发安全验证，等待15秒后重试")
            time.sleep(15)
            driver.get(url)
            time.sleep(random.uniform(3, 6))

        api_url = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"
        params = {
            "scene": "1",
            "query": query,
            "city": city,
            "experience": "104,105,106",
            "page": page,
            "pageSize": page_size,
        }
        query_string = urllib.parse.urlencode(params)
        full_url = f"{api_url}?{query_string}"

        resp = driver.get(full_url)
        time.sleep(2)

        try:
            data = resp.json
        except Exception:
            try:
                body = resp.text
                data = json.loads(body)
            except Exception:
                page_source = driver.html
                if page_source:
                    try:
                        start = page_source.find('{')
                        end = page_source.rfind('}') + 1
                        if start >= 0 and end > start:
                            data = json.loads(page_source[start:end])
                        else:
                            logger.error("浏览器模式: 无法从页面解析JSON")
                            return []
                    except Exception:
                        logger.error("浏览器模式: JSON解析失败")
                        return []
                else:
                    return []

        code = data.get('code')
        message = data.get('message', '')
        job_list = data.get("zpData", {}).get("jobList", [])

        if code == 36:
            set_cookie_error(f"账户异常(code=36): {message}")
            return []

        if code == 1:
            logger.warning("浏览器模式: 业务错误 code=1 - %s", message)
            set_cookie_error(f"Cookie失效(code=1): {message}")
            return []

        if code is not None and code != 0:
            logger.warning("浏览器模式: 非预期 code=%s - %s", code, message)

        logger.info("浏览器模式: 搜索 '%s' 城市=%s: 获取 %d 条", query, city, len(job_list))
        return job_list

    except Exception as e:
        logger.error("浏览器模式异常: %s", e)
        return []
    finally:
        safe_quit_driver(driver)


def search_boss_jobs_http(query: str, city: str, page: int = 1, page_size: int = 30, max_retries: int = 3) -> list:
    try:
        from curl_cffi import requests as curl_requests
        use_curl = True
    except ImportError:
        import requests as std_requests
        use_curl = False

    config = get_config()
    boss_cookie = config.get('boss_cookie', '')

    url = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"

    headers_list = [
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.zhipin.com/web/geek/job",
            "Origin": "https://www.zhipin.com",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
        },
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.zhipin.com/web/geek/job",
            "Origin": "https://www.zhipin.com",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
        },
    ]

    headers = random.choice(headers_list).copy()
    headers["Cookie"] = boss_cookie

    params = {
        "scene": "1",
        "query": query,
        "city": city,
        "experience": "104,105,106",
        "page": page,
        "pageSize": page_size,
    }

    for attempt in range(max_retries):
        try:
            if use_curl:
                resp = curl_requests.get(url, headers=headers, params=params, timeout=20, impersonate="chrome131")
            else:
                resp = std_requests.get(url, headers=headers, params=params, timeout=20)

            if resp.status_code == 403:
                wait = (attempt + 1) * 30 + random.uniform(10, 30)
                logger.warning("HTTP模式: 403 Forbidden (尝试 %d/%d)，等待 %.0fs", attempt + 1, max_retries, wait)
                time.sleep(wait)
                headers = random.choice(headers_list).copy()
                headers["Cookie"] = boss_cookie
                continue

            if resp.status_code == 429:
                wait = (attempt + 1) * 30 + random.uniform(15, 45)
                logger.warning("HTTP模式: 429 限流 (尝试 %d/%d)，等待 %.0fs", attempt + 1, max_retries, wait)
                time.sleep(wait)
                headers = random.choice(headers_list).copy()
                headers["Cookie"] = boss_cookie
                continue

            if resp.status_code != 200:
                logger.error("HTTP模式: HTTP %d", resp.status_code)
                if attempt < max_retries - 1:
                    time.sleep((attempt + 1) * 15)
                continue

            data = resp.json()
            code = data.get("code")
            message = data.get("message", "")

            if code == 36:
                set_cookie_error(f"账户异常(code=36): {message}")
                return []

            if code == 1:
                logger.warning("HTTP模式: 业务错误 code=1 - %s", message)
                if "登录" in message or "安全" in message or "验证" in message:
                    set_cookie_error(f"Cookie失效(code=1): {message}")
                    return []
                if attempt < max_retries - 1:
                    time.sleep((attempt + 1) * 20 + random.uniform(5, 15))
                continue

            if code is not None and code != 0:
                logger.warning("HTTP模式: 非预期 code=%s - %s", code, message)

            job_list = data.get("zpData", {}).get("jobList", [])
            logger.info("HTTP模式: 搜索 '%s' 城市=%s: 获取 %d 条", query, city, len(job_list))
            return job_list

        except json.JSONDecodeError:
            logger.error("HTTP模式: 响应非JSON (尝试 %d/%d)", attempt + 1, max_retries)
            if attempt < max_retries - 1:
                time.sleep((attempt + 1) * 20 + random.uniform(5, 15))
            continue
        except Exception as e:
            logger.error("HTTP模式: 搜索失败 (尝试 %d/%d): %s", attempt + 1, max_retries, e)
            if attempt < max_retries - 1:
                time.sleep(10)
            continue

    logger.error("HTTP模式: %d次重试均失败", max_retries)
    return []


def search_boss_jobs(query: str, city: str, page: int = 1, page_size: int = 30) -> list:
    config = get_config()
    boss_cookie = config.get('boss_cookie', '')
    scrape_mode = config.get('scrape_mode', 'auto')

    if not boss_cookie:
        logger.warning("BOSS_COOKIE 未设置，跳过抓取")
        return []

    if scrape_mode in ('browser', 'auto'):
        logger.info("尝试浏览器模式抓取 '%s' ...", query)
        result = search_boss_jobs_browser(query, city, page, page_size)
        if result is not None:
            return result
        if scrape_mode == 'browser':
            return []
        logger.info("浏览器模式失败，降级到HTTP模式")

    logger.info("使用HTTP模式抓取 '%s' ...", query)
    return search_boss_jobs_http(query, city, page, page_size)