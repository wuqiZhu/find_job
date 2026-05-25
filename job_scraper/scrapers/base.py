"""抓取器公共工具"""
import time
import random
import logging

logger = logging.getLogger(__name__)

COOKIE_ERROR = None


def set_cookie_error(msg: str):
    global COOKIE_ERROR
    COOKIE_ERROR = msg
    logger.error(msg)


def random_delay(low: float = 2.0, high: float = 5.0) -> float:
    delay = random.uniform(low, high)
    time.sleep(delay)
    return delay


def parse_cookie_to_list(cookie_str: str, domain: str = ".zhipin.com") -> list:
    cookies = []
    for item in cookie_str.split(';'):
        item = item.strip()
        if '=' in item:
            name, value = item.split('=', 1)
            cookies.append({"name": name.strip(), "value": value.strip(), "domain": domain, "path": "/"})
    return cookies


def create_chrome_options():
    try:
        from DrissionPage import ChromiumOptions
    except ImportError:
        logger.error("DrissionPage 未安装，请执行 pip install DrissionPage")
        raise

    co = ChromiumOptions()
    co.headless(True)
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_argument('--window-size=1920,1080')
    co.set_user_agent(
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/131.0.0.0 Safari/537.36'
    )
    return co


def safe_quit_driver(driver):
    if driver is None:
        return
    try:
        driver.quit()
    except Exception:
        pass


def normalize_job(raw: dict, platform: str) -> dict:
    return {
        'jobName': raw.get('jobName', raw.get('job_name', '')),
        'brandName': raw.get('brandName', raw.get('company', '')),
        'salaryDesc': raw.get('salaryDesc', raw.get('salary', '')),
        'areaDistrict': raw.get('areaDistrict', raw.get('location', '')),
        'skills': raw.get('skills', []),
        'jobExperience': raw.get('jobExperience', raw.get('experience', '')),
        'bossTitle': raw.get('bossTitle', ''),
        'bossOnline': raw.get('bossOnline', False),
        'encryptJobId': raw.get('encryptJobId', raw.get('job_id', '')),
        'url': raw.get('url', ''),
        'platform': platform,
    }
