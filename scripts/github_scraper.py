#!/usr/bin/env python3
"""
GitHub Actions 定时岗位抓取脚本
- 从 Boss 直聘搜索岗位（DrissionPage 浏览器自动化优先，HTTP API 降级）
- 用小米 MiMo API 评分
- 高分岗位通过钉钉通知
"""

import os
import sys
import json
import time
import hmac
import hashlib
import base64
import urllib.parse
import random
from datetime import datetime


PROFILE = {}


def load_profile():
    global PROFILE
    profile_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'profile.json')
    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            PROFILE = json.load(f)
            print(f"[INFO] 已加载 profile.json")
            return PROFILE
    except FileNotFoundError:
        print("[WARN] profile.json 未找到，使用默认配置")
        return {}
    except json.JSONDecodeError as e:
        print(f"[ERROR] profile.json 解析失败: {e}")
        return {}


def check_blacklist(job_name, company, experience):
    blacklist = PROFILE.get('blacklist_keywords', [])
    text = f"{job_name} {company} {experience}"
    for keyword in blacklist:
        if keyword in text:
            return True, keyword
    return False, None

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')


def load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
    if not os.path.exists(env_path):
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


load_env_file()

BOSS_COOKIE = os.environ.get('BOSS_COOKIE', '')
DINGTALK_WEBHOOK = os.environ.get('DINGTALK_WEBHOOK', '')
DINGTALK_SECRET = os.environ.get('DINGTALK_SECRET', '')
MIMO_API_KEY = os.environ.get('MIMO_API_KEY', '')
MIMO_BASE_URL = os.environ.get('MIMO_BASE_URL', 'https://token-plan-cn.xiaomimimo.com/v1')
MIMO_MODEL = os.environ.get('MIMO_MODEL', 'mimo-v2.5-pro')
SCRAPE_MODE = os.environ.get('SCRAPE_MODE', 'auto')
LIEPIN_COOKIE = os.environ.get('LIEPIN_COOKIE', '')
ZHAOPIN_COOKIE = os.environ.get('ZHAOPIN_COOKIE', '')
ZHAOPIN_AT = os.environ.get('ZHAOPIN_AT', '')
ZHAOPIN_RT = os.environ.get('ZHAOPIN_RT', '')

SEARCH_QUERIES = [
    {"platform": "boss", "query": "嵌入式Linux开发", "city": "101280600", "city_name": "深圳"},
    {"platform": "boss", "query": "嵌入式Linux开发", "city": "101020100", "city_name": "上海"},
    {"platform": "boss", "query": "BSP工程师", "city": "101280600", "city_name": "深圳"},
    {"platform": "boss", "query": "Linux驱动开发", "city": "101280600", "city_name": "深圳"},
    {"platform": "liepin", "query": "嵌入式Linux", "city": "040", "city_name": "深圳"},
    {"platform": "liepin", "query": "BSP工程师", "city": "040", "city_name": "深圳"},
    {"platform": "lagou", "query": "嵌入式Linux", "city": "深圳", "city_name": "深圳"},
    {"platform": "lagou", "query": "BSP工程师", "city": "深圳", "city_name": "深圳"},
    {"platform": "niuke", "query": "嵌入式Linux", "city": "深圳", "city_name": "深圳"},
    {"platform": "niuke", "query": "BSP工程师", "city": "深圳", "city_name": "深圳"},
    {"platform": "zhaopin", "query": "嵌入式Linux", "city": "763", "city_name": "深圳"},
    {"platform": "zhaopin", "query": "BSP工程师", "city": "763", "city_name": "深圳"},
    {"platform": "shixiseng", "query": "嵌入式Linux", "city": "深圳", "city_name": "深圳"},
    {"platform": "shixiseng", "query": "BSP工程师", "city": "深圳", "city_name": "深圳"},
    {"platform": "shixiseng", "query": "嵌入式开发", "city": "深圳", "city_name": "深圳"},
]

SCORE_THRESHOLD = 80
DATA_FILE = "data/seen_jobs.json"

COOKIE_ERROR = None


def random_delay(min_s=5, max_s=12):
    delay = random.uniform(min_s, max_s)
    time.sleep(delay)
    return delay


def load_seen_jobs():
    try:
        os.makedirs("data", exist_ok=True)
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_seen_jobs(seen):
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)


def parse_cookie_to_list(cookie_str):
    cookies = []
    for item in cookie_str.split(';'):
        item = item.strip()
        if '=' in item:
            name, value = item.split('=', 1)
            cookies.append({"name": name.strip(), "value": value.strip(), "domain": ".zhipin.com", "path": "/"})
    return cookies


def search_boss_jobs_browser(query, city, page=1, page_size=30):
    try:
        from DrissionPage import ChromiumPage, ChromiumOptions
    except ImportError:
        print("[WARN] DrissionPage 未安装，跳过浏览器模式")
        return None

    co = ChromiumOptions()
    co.headless(True)
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_argument('--window-size=1920,1080')
    co.set_user_agent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

    driver = None
    try:
        driver = ChromiumPage(co)

        if BOSS_COOKIE:
            driver.get("https://www.zhipin.com")
            time.sleep(2)
            for c in parse_cookie_to_list(BOSS_COOKIE):
                try:
                    driver.set.cookies(c)
                except Exception:
                    pass
            time.sleep(1)

        url = f"https://www.zhipin.com/web/geek/job?query={urllib.parse.quote(query)}&city={city}&experience=104,105,106"
        driver.get(url)
        time.sleep(random.uniform(3, 6))

        if '安全验证' in driver.html or 'verify' in driver.url.lower():
            print(f"[WARN] 触发安全验证，等待15秒后重试")
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
                            print(f"[ERROR] 浏览器模式: 无法从页面解析JSON")
                            return []
                    except Exception:
                        print(f"[ERROR] 浏览器模式: JSON解析失败")
                        return []
                else:
                    return []

        code = data.get('code')
        message = data.get('message', '')
        job_list = data.get("zpData", {}).get("jobList", [])

        if code == 36:
            print(f"[ERROR] 浏览器模式: 账户被标记异常 (code=36): {message}")
            print("[ERROR] 请在浏览器中手动登录 Boss 直聘，完成验证后重新获取 Cookie")
            global COOKIE_ERROR
            COOKIE_ERROR = f"账户异常(code=36): {message}"
            return []

        if code == 1:
            print(f"[WARN] 浏览器模式: 业务错误 code=1 - {message}")
            COOKIE_ERROR = f"Cookie失效(code=1): {message}"
            return []

        if code is not None and code != 0:
            print(f"[WARN] 浏览器模式: 非预期 code={code} - {message}")

        print(f"[INFO] 浏览器模式: 搜索 '{query}' 城市={city}: 获取 {len(job_list)} 条")
        return job_list

    except Exception as e:
        print(f"[ERROR] 浏览器模式异常: {e}")
        return []
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def search_boss_jobs_http(query, city, page=1, page_size=30, max_retries=3):
    try:
        from curl_cffi import requests as curl_requests
        use_curl = True
    except ImportError:
        import requests as std_requests
        use_curl = False

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
    headers["Cookie"] = BOSS_COOKIE

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
                print(f"[WARN] HTTP模式: 403 Forbidden (尝试 {attempt + 1}/{max_retries})，等待 {wait:.0f}s")
                time.sleep(wait)
                headers = random.choice(headers_list).copy()
                headers["Cookie"] = BOSS_COOKIE
                continue

            if resp.status_code == 429:
                wait = (attempt + 1) * 30 + random.uniform(15, 45)
                print(f"[WARN] HTTP模式: 429 限流 (尝试 {attempt + 1}/{max_retries})，等待 {wait:.0f}s")
                time.sleep(wait)
                headers = random.choice(headers_list).copy()
                headers["Cookie"] = BOSS_COOKIE
                continue

            if resp.status_code != 200:
                print(f"[ERROR] HTTP模式: HTTP {resp.status_code}")
                if attempt < max_retries - 1:
                    time.sleep((attempt + 1) * 15)
                continue

            data = resp.json()
            code = data.get("code")
            message = data.get("message", "")

            if code == 36:
                print(f"[ERROR] 账户被标记异常 (code=36): {message}")
                print("[ERROR] 请在浏览器中手动登录 Boss 直聘，完成验证后重新获取 Cookie")
                print("[ERROR] 步骤: 1) 打开 zhipin.com 登录 2) 完成安全验证 3) 运行 python get_cookie.py 更新")
                global COOKIE_ERROR
                COOKIE_ERROR = f"账户异常(code=36): {message}"
                return []

            if code == 1:
                print(f"[WARN] HTTP模式: 业务错误 code=1 - {message}")
                if "登录" in message or "安全" in message or "验证" in message:
                    print("[ERROR] Cookie可能已失效，请更新BOSS_COOKIE")
                    COOKIE_ERROR = f"Cookie失效(code=1): {message}"
                    return []
                if attempt < max_retries - 1:
                    time.sleep((attempt + 1) * 20 + random.uniform(5, 15))
                continue

            if code is not None and code != 0:
                print(f"[WARN] HTTP模式: 非预期 code={code} - {message}")

            job_list = data.get("zpData", {}).get("jobList", [])
            print(f"[INFO] HTTP模式: 搜索 '{query}' 城市={city}: 获取 {len(job_list)} 条")
            return job_list

        except json.JSONDecodeError:
            print(f"[ERROR] HTTP模式: 响应非JSON (尝试 {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep((attempt + 1) * 20 + random.uniform(5, 15))
            continue
        except Exception as e:
            print(f"[ERROR] HTTP模式: 搜索失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(10)
            continue

    print(f"[ERROR] HTTP模式: {max_retries}次重试均失败")
    return []


def search_boss_jobs(query, city, page=1, page_size=30):
    if not BOSS_COOKIE:
        print("[WARN] BOSS_COOKIE 未设置，跳过抓取")
        return []

    if SCRAPE_MODE in ('browser', 'auto'):
        print(f"[INFO] 尝试浏览器模式抓取 '{query}' ...")
        result = search_boss_jobs_browser(query, city, page, page_size)
        if result is not None:
            return result
        if SCRAPE_MODE == 'browser':
            return []
        print("[INFO] 浏览器模式失败，降级到HTTP模式")

    print(f"[INFO] 使用HTTP模式抓取 '{query}' ...")
    return search_boss_jobs_http(query, city, page, page_size)


def search_liepin_jobs(query, city="040", page=1, page_size=20):
    if not LIEPIN_COOKIE:
        print("[WARN] LIEPIN_COOKIE 未设置，跳过猎聘抓取")
        return []

    try:
        from DrissionPage import ChromiumPage, ChromiumOptions
    except ImportError:
        print("[WARN] DrissionPage 未安装，跳过猎聘抓取")
        return []

    co = ChromiumOptions()
    co.headless(True)
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_argument('--window-size=1920,1080')
    co.set_user_agent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

    driver = None
    try:
        driver = ChromiumPage(co)

        driver.get("https://www.liepin.com")
        time.sleep(2)

        for item in LIEPIN_COOKIE.split(';'):
            item = item.strip()
            if '=' in item:
                name, value = item.split('=', 1)
                try:
                    driver.set.cookies({"name": name.strip(), "value": value.strip(), "domain": ".liepin.com", "path": "/"})
                except Exception:
                    pass
        time.sleep(1)

        encoded_key = urllib.parse.quote(query)
        url = f"https://www.liepin.com/zhaopin/?key={encoded_key}&dq={city}"
        driver.get(url)
        time.sleep(random.uniform(3, 6))

        api_url = "https://api-c.liepin.com/api/com.liepin.searchfront4c.pc-search-job"
        payload = {
            "data": {
                "mainSearchPc": {
                    "pcSearchForm": {
                        "city": city,
                        "dq": city,
                        "currentPage": page - 1,
                        "pageSize": page_size,
                        "key": query,
                        "workYearCode": "0,1,2,3",
                        "searchType": 1,
                        "scene": "input",
                        "sfrom": "search_job_pc",
                    }
                }
            }
        }

        resp = driver.post(api_url, json=payload)
        time.sleep(2)

        try:
            data = resp.json
        except Exception:
            try:
                data = json.loads(resp.text)
            except Exception:
                page_source = driver.html
                if page_source:
                    try:
                        start = page_source.find('{')
                        end = page_source.rfind('}') + 1
                        if start >= 0 and end > start:
                            data = json.loads(page_source[start:end])
                        else:
                            print(f"[ERROR] 猎聘: 无法解析JSON")
                            return []
                    except Exception:
                        print(f"[ERROR] 猎聘: JSON解析失败")
                        return []
                else:
                    return []

        code = data.get('code')
        msg = data.get('msg', '')

        if str(code) != '0':
            print(f"[WARN] 猎聘: code={code}, msg={msg}")
            return []

        result = data.get('data', {})
        job_list = result.get('list', [])

        normalized_jobs = []
        for job in job_list:
            job_info = job.get('job', {})
            comp_info = job.get('comp', {})

            normalized = {
                'jobName': job_info.get('title', ''),
                'brandName': comp_info.get('compName', ''),
                'salaryDesc': job_info.get('salary', ''),
                'areaDistrict': job_info.get('dq', ''),
                'skills': job_info.get('labels', []),
                'jobExperience': job_info.get('workYear', ''),
                'bossTitle': '',
                'bossOnline': False,
                'encryptJobId': job_info.get('jobId', ''),
                'url': f"https://www.liepin.com/job/{job_info.get('jobId', '')}.shtml",
                'platform': 'liepin',
            }
            normalized_jobs.append(normalized)

        print(f"[INFO] 猎聘: 搜索 '{query}' 城市={city}: 获取 {len(normalized_jobs)} 条")
        return normalized_jobs

    except Exception as e:
        print(f"[ERROR] 猎聘: 抓取异常: {e}")
        return []
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def search_lagou_jobs(query, city="深圳", page=1, page_size=15):
    try:
        from DrissionPage import ChromiumPage, ChromiumOptions
    except ImportError:
        print("[WARN] DrissionPage 未安装，跳过拉勾抓取")
        return []

    co = ChromiumOptions()
    co.headless(True)
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_argument('--window-size=1920,1080')
    co.set_user_agent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

    driver = None
    try:
        driver = ChromiumPage(co)

        encoded_key = urllib.parse.quote(query)
        url = f"https://www.lagou.com/wn/zhaopin?kd={encoded_key}&city={urllib.parse.quote(city)}"
        driver.get(url)
        time.sleep(random.uniform(4, 7))

        api_url = "https://www.lagou.com/jobs/v2/positionAjax.json"
        data = {
            "first": "true",
            "pn": str(page),
            "kd": query,
            "city": city,
        }

        resp = driver.post(api_url, data=data)
        time.sleep(2)

        try:
            result = resp.json
        except Exception:
            try:
                result = json.loads(resp.text)
            except Exception:
                print(f"[ERROR] 拉勾: JSON解析失败")
                return []

        code = result.get('code')
        if code != 0:
            print(f"[WARN] 拉勾: code={code}")
            return []

        content = result.get('content', {})
        results = content.get('result', [])

        normalized_jobs = []
        for job in results:
            company = job.get('companyFullName', '')
            position = job.get('positionName', '')
            salary = job.get('salary', '')
            job_city = job.get('city', '')
            district = job.get('district', '')
            experience = job.get('workYear', '')
            education = job.get('education', '')
            position_id = job.get('positionId', '')
            company_id = job.get('companyId', '')

            skills = []
            if job.get('skillLables'):
                skills = job['skillLables']
            elif job.get('industryLables'):
                skills = job['industryLables']

            normalized = {
                'jobName': position,
                'brandName': company,
                'salaryDesc': salary,
                'areaDistrict': f"{job_city} {district}".strip(),
                'skills': skills,
                'jobExperience': experience,
                'bossTitle': '',
                'bossOnline': False,
                'encryptJobId': str(position_id),
                'url': f"https://www.lagou.com/wn/jobs/{position_id}.html",
                'platform': 'lagou',
            }
            normalized_jobs.append(normalized)

        print(f"[INFO] 拉勾: 搜索 '{query}' 城市={city}: 获取 {len(normalized_jobs)} 条")
        return normalized_jobs

    except Exception as e:
        print(f"[ERROR] 拉勾: 抓取异常: {e}")
        return []
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def search_niuke_jobs(query, city="深圳", page=1, page_size=20):
    try:
        from DrissionPage import ChromiumPage, ChromiumOptions
    except ImportError:
        print("[WARN] DrissionPage 未安装，跳过牛客抓取")
        return []

    co = ChromiumOptions()
    co.headless(True)
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_argument('--window-size=1920,1080')
    co.set_user_agent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

    driver = None
    try:
        driver = ChromiumPage(co)

        encoded_key = urllib.parse.quote(query)
        url = f"https://www.nowcoder.com/search/all?query={encoded_key}&type=job"
        driver.get(url)
        time.sleep(random.uniform(4, 7))

        job_items = driver.eles('css:.search-job-result .job-list-item, css:.nc-job-list .job-item, css:[class*="job"] .item, css:.search-result-list .result-item')

        if not job_items:
            job_items = driver.eles('css:a[href*="/job/"]')

        normalized_jobs = []
        for item in job_items[:page_size]:
            try:
                title_el = item.ele('css:.job-name, css:.position-name, css:h3, css:a[class*="title"]')
                company_el = item.ele('css:.company-name, css:.company, css:span[class*="company"]')
                salary_el = item.ele('css:.salary, css:span[class*="salary"]')
                location_el = item.ele('css:.location, css:span[class*="location"], css:.city')

                job_title = title_el.text.strip() if title_el else ''
                company = company_el.text.strip() if company_el else ''
                salary = salary_el.text.strip() if salary_el else ''
                location = location_el.text.strip() if location_el else city

                link_el = item.ele('css:a[href*="/job/"]')
                job_url = link_el.attr('href') if link_el else ''
                if job_url and not job_url.startswith('http'):
                    job_url = f"https://www.nowcoder.com{job_url}"

                job_id = ''
                if '/job/' in job_url:
                    job_id = job_url.split('/job/')[-1].split('?')[0].split('.')[0]

                if not job_title:
                    continue

                normalized = {
                    'jobName': job_title,
                    'brandName': company,
                    'salaryDesc': salary,
                    'areaDistrict': location,
                    'skills': [],
                    'jobExperience': '',
                    'bossTitle': '',
                    'bossOnline': False,
                    'encryptJobId': job_id,
                    'url': job_url,
                    'platform': 'niuke',
                }
                normalized_jobs.append(normalized)
            except Exception:
                continue

        print(f"[INFO] 牛客: 搜索 '{query}' 城市={city}: 获取 {len(normalized_jobs)} 条")
        return normalized_jobs

    except Exception as e:
        print(f"[ERROR] 牛客: 抓取异常: {e}")
        return []
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def search_zhaopin_jobs(query, city="763", page=1, page_size=20):
    if not ZHAOPIN_COOKIE:
        print("[WARN] ZHAOPIN_COOKIE 未设置，跳过智联抓取")
        return []

    try:
        from curl_cffi import requests as curl_requests
        use_curl = True
    except ImportError:
        import requests as std_requests
        use_curl = False

    url = "https://fe-api.zhaopin.com/c/i/sou"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://sou.zhaopin.com/",
        "Origin": "https://www.zhaopin.com",
        "Cookie": ZHAOPIN_COOKIE,
    }

    params = {
        "pageSize": str(page_size),
        "cityId": city,
        "workExperience": "-1",
        "education": "-1",
        "companyType": "-1",
        "employmentType": "-1",
        "jobWelfareTag": "-1",
        "kw": query,
        "kt": "3",
    }

    if ZHAOPIN_AT:
        params["at"] = ZHAOPIN_AT
    if ZHAOPIN_RT:
        params["rt"] = ZHAOPIN_RT

    for attempt in range(3):
        try:
            if use_curl:
                resp = curl_requests.get(url, headers=headers, params=params, timeout=20, impersonate="chrome131")
            else:
                resp = std_requests.get(url, headers=headers, params=params, timeout=20)

            if resp.status_code != 200:
                print(f"[WARN] 智联: HTTP {resp.status_code} (尝试 {attempt + 1}/3)")
                time.sleep(5)
                continue

            data = resp.json()
            code = data.get('code')

            if code != 200:
                print(f"[WARN] 智联: code={code} (尝试 {attempt + 1}/3)")
                time.sleep(5)
                continue

            result = data.get('data', {})
            job_list = result.get('list', result.get('results', []))

            normalized_jobs = []
            for job in job_list:
                job_name = job.get('jobName', '')
                company_info = job.get('company', {})
                company_name = company_info.get('name', '')
                salary = job.get('salary', '')
                city_name = job.get('city', {}).get('display', '') if isinstance(job.get('city'), dict) else str(job.get('city', ''))
                job_number = job.get('number', '')
                work_exp = job.get('workExp', {}).get('display', '') if isinstance(job.get('workExp'), dict) else str(job.get('workExp', ''))

                job_url = f"https://jobs.zhaopin.com/{job_number}.htm"

                normalized = {
                    'jobName': job_name,
                    'brandName': company_name,
                    'salaryDesc': salary,
                    'areaDistrict': city_name,
                    'skills': [],
                    'jobExperience': work_exp,
                    'bossTitle': '',
                    'bossOnline': False,
                    'encryptJobId': job_number,
                    'url': job_url,
                    'platform': 'zhaopin',
                }
                normalized_jobs.append(normalized)

            print(f"[INFO] 智联: 搜索 '{query}' 城市={city}: 获取 {len(normalized_jobs)} 条")
            return normalized_jobs

        except json.JSONDecodeError:
            print(f"[WARN] 智联: JSON解析失败 (尝试 {attempt + 1}/3)")
            time.sleep(5)
        except Exception as e:
            print(f"[ERROR] 智联: 请求失败 (尝试 {attempt + 1}/3): {e}")
            time.sleep(5)

    print(f"[ERROR] 智联: 3次重试均失败")
    return []


def search_shixiseng_jobs(query, city="深圳", page=1, page_size=10):
    try:
        from DrissionPage import ChromiumPage, ChromiumOptions
    except ImportError:
        print("[WARN] DrissionPage 未安装，跳过实习僧抓取")
        return []

    co = ChromiumOptions()
    co.headless(True)
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_argument('--window-size=1920,1080')
    co.set_user_agent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

    driver = None
    try:
        driver = ChromiumPage(co)

        encoded_key = urllib.parse.quote(query)
        encoded_city = urllib.parse.quote(city)
        url = f"https://www.shixiseng.com/interns?k={encoded_key}&c={encoded_city}&p={page}"
        driver.get(url)
        time.sleep(random.uniform(4, 7))

        job_items = driver.eles('css:.intern-list .list-item, css:.intern-wrap .item, css:[class*="intern"] .job-item, css:.position-list .item')

        if not job_items:
            job_items = driver.eles('css:a[href*="/intern/"]')

        normalized_jobs = []
        for item in job_items[:page_size]:
            try:
                title_el = item.ele('css:.title, css:a[class*="title"], css:h3, css:.job-name')
                company_el = item.ele('css:.company, css:a[class*="company"], css:.company-name')
                salary_el = item.ele('css:.salary, css:span[class*="salary"]')
                city_el = item.ele('css:.city, css:span[class*="city"], css:.location')

                job_title = title_el.text.strip() if title_el else ''
                company = company_el.text.strip() if company_el else ''
                salary = salary_el.text.strip() if salary_el else ''
                job_city = city_el.text.strip() if city_el else city

                link_el = item.ele('css:a[href*="/intern/"]')
                job_url = link_el.attr('href') if link_el else ''
                if job_url and not job_url.startswith('http'):
                    job_url = f"https://www.shixiseng.com{job_url}"

                job_id = ''
                if '/intern/' in job_url:
                    job_id = job_url.split('/intern/')[-1].split('?')[0].split('.')[0]

                if not job_title:
                    continue

                normalized = {
                    'jobName': job_title,
                    'brandName': company,
                    'salaryDesc': salary,
                    'areaDistrict': job_city,
                    'skills': [],
                    'jobExperience': '实习',
                    'bossTitle': '',
                    'bossOnline': False,
                    'encryptJobId': job_id,
                    'url': job_url,
                    'platform': 'shixiseng',
                }
                normalized_jobs.append(normalized)
            except Exception:
                continue

        print(f"[INFO] 实习僧: 搜索 '{query}' 城市={city}: 获取 {len(normalized_jobs)} 条")
        return normalized_jobs

    except Exception as e:
        print(f"[ERROR] 实习僧: 抓取异常: {e}")
        return []
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def extract_mimo_response_text(result):
    if "choices" in result:
        try:
            return result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            pass

    for field in ["result", "response", "output", "text", "content"]:
        val = result.get(field)
        if isinstance(val, str) and val.strip():
            return val.strip()

    data = result.get("data")
    if isinstance(data, dict):
        if "choices" in data:
            try:
                return data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                pass
        for field in ["result", "response", "output", "text", "content"]:
            val = data.get(field)
            if isinstance(val, str) and val.strip():
                return val.strip()

    print(f"[WARN] 无法解析MiMo响应，原始响应: {json.dumps(result, ensure_ascii=False)[:500]}")
    return None


def evaluate_with_mimo(jd_text, max_retries=2):
    if not MIMO_API_KEY:
        print("[WARN] MIMO_API_KEY 未设置，跳过评分")
        return None

    try:
        from curl_cffi import requests as curl_requests
        use_curl = True
    except ImportError:
        import requests as std_requests
        use_curl = False

    url = f"{MIMO_BASE_URL}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MIMO_API_KEY}",
    }

    # 从 profile.json 动态生成 prompt
    if PROFILE:
        edu = PROFILE.get('education', {})
        skills = PROFILE.get('skills', {})
        projects = PROFILE.get('projects', [])
        certificates = PROFILE.get('certificates', [])
        standards = PROFILE.get('scoring_standards', {})

        # 构建技能描述
        skill_lines = []
        for category, items in skills.items():
            skill_lines.extend([f"- {item}" for item in items])

        # 构建项目描述
        project_lines = [f"- {p['name']}（{p['tech_stack']}）" for p in projects]

        # 构建评分标准
        standard_lines = [f"- {score}: {desc}" for score, desc in standards.items()]

        background = f"""## 我的背景
- {edu.get('grade', '')}，{edu.get('school', '')}，{edu.get('major', '')}专业
- 求职意向：{PROFILE.get('target', '')}
{chr(10).join(skill_lines)}
- 项目经验：{', '.join([p['name'] for p in projects])}
- {', '.join(certificates)}"""

        scoring_standards = f"""## 评分标准（注意：我是找实习的在校生，不是社招）
{chr(10).join(standard_lines)}"""
    else:
        # 默认 prompt（profile.json 未加载时使用）
        background = """## 我的背景
- 大三本科生，长春大学旅游学院，物联网工程专业
- 求职意向：嵌入式软件/Linux应用开发实习生
- 熟练掌握C，熟悉C++面向对象编程，了解Python
- 熟悉Linux系统编程（进程、线程、文件I/O、Socket），掌握TCP/UDP协议及epoll高并发模型
- 了解嵌入式Linux开发流程，掌握UART、I2C、SPI等通信协议
- 项目经验：基于MQTT的智能家居控制系统
- 英语六级（CET-6），国家励志奖学金"""

        scoring_standards = """## 评分标准（注意：我是找实习的在校生，不是社招）
- 90-100: 完美匹配，必须投递（嵌入式/Linux开发实习，技术栈高度匹配）
- 80-89: 高度匹配，建议投递（嵌入式/Linux相关实习，大部分技能匹配）
- 70-79: 一般匹配，可考虑（相关领域实习，部分技能可迁移）
- 60以下: 不太匹配（方向不相关，如纯前端、纯Java后端等）"""

    prompt = f"""你是一个求职匹配评估专家。请根据以下简历信息和职位描述，给出0-100的匹配度评分。

{background}

{scoring_standards}

## 职位描述
{jd_text}

请只返回一个JSON格式：{{"score": 分数, "reason": "简短理由"}}
"""

    payload = {
        "model": MIMO_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个专业的求职匹配评估专家，只返回JSON格式的评分结果。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 300,
    }

    for attempt in range(max_retries):
        try:
            if use_curl:
                resp = curl_requests.post(url, headers=headers, json=payload, timeout=30, impersonate="chrome131")
            else:
                resp = std_requests.post(url, headers=headers, json=payload, timeout=30)

            if resp.status_code == 429:
                print(f"[WARN] MiMo API限流，等待 {(attempt + 1) * 5}s")
                time.sleep((attempt + 1) * 5)
                continue

            if resp.status_code != 200:
                print(f"[ERROR] MiMo API返回 HTTP {resp.status_code}: {resp.text[:200]}")
                if attempt < max_retries - 1:
                    time.sleep(3)
                continue

            result = resp.json()
            text = extract_mimo_response_text(result)
            if not text:
                return None
            text = text.strip().replace("```json", "").replace("```", "").strip()
            return json.loads(text)

        except json.JSONDecodeError as e:
            print(f"[ERROR] MiMo评分响应解析失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(3)
        except Exception as e:
            print(f"[ERROR] MiMo评分失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(3)

    return None


def save_feedback_record(job, action="notified"):
    """保存岗位反馈记录到本地文件"""
    feedback_file = os.path.join(DATA_DIR, "feedback_records.json")
    try:
        records = {}
        if os.path.exists(feedback_file):
            with open(feedback_file, "r", encoding="utf-8") as f:
                records = json.load(f)

        job_id = make_job_id(job)
        records[job_id] = {
            "company": job.get("company", job.get("brandName", "")),
            "role": job.get("role", job.get("jobName", "")),
            "score": job.get("score", 0),
            "salary": job.get("salary", job.get("salaryDesc", "")),
            "location": job.get("location", job.get("areaDistrict", "")),
            "url": job.get("url", ""),
            "action": action,
            "notified_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

        with open(feedback_file, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[WARN] 保存反馈记录失败: {e}")
        return False


def update_feedback_record(job_id, action):
    """更新岗位反馈状态"""
    feedback_file = os.path.join(DATA_DIR, "feedback_records.json")
    try:
        records = {}
        if os.path.exists(feedback_file):
            with open(feedback_file, "r", encoding="utf-8") as f:
                records = json.load(f)

        if job_id in records:
            records[job_id]["action"] = action
            records[job_id]["updated_at"] = datetime.now().isoformat()

            with open(feedback_file, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            return True
    except Exception as e:
        print(f"[WARN] 更新反馈记录失败: {e}")
    return False


def get_feedback_stats():
    """获取反馈统计信息"""
    feedback_file = os.path.join(DATA_DIR, "feedback_records.json")
    try:
        if not os.path.exists(feedback_file):
            return {"total": 0, "stats": {}}

        with open(feedback_file, "r", encoding="utf-8") as f:
            records = json.load(f)

        stats = {
            "total": len(records),
            "notified": 0,
            "applied": 0,
            "rejected": 0,
            "viewed": 0,
            "by_company": {},
            "by_score_range": {"90-100": 0, "80-89": 0, "70-79": 0, "0-69": 0}
        }

        for job_id, record in records.items():
            action = record.get("action", "notified")
            if action == "notified":
                stats["notified"] += 1
            elif action == "applied":
                stats["applied"] += 1
            elif action == "rejected":
                stats["rejected"] += 1
            elif action == "viewed":
                stats["viewed"] += 1

            # 按公司统计
            company = record.get("company", "未知")
            stats["by_company"][company] = stats["by_company"].get(company, 0) + 1

            # 按评分范围统计
            score = record.get("score", 0)
            if score >= 90:
                stats["by_score_range"]["90-100"] += 1
            elif score >= 80:
                stats["by_score_range"]["80-89"] += 1
            elif score >= 70:
                stats["by_score_range"]["70-79"] += 1
            else:
                stats["by_score_range"]["0-69"] += 1

        return stats
    except Exception as e:
        print(f"[WARN] 获取反馈统计失败: {e}")
        return {"total": 0, "stats": {}}


def generate_feedback_report():
    """生成反馈统计报告"""
    stats = get_feedback_stats()
    if stats["total"] == 0:
        return "暂无反馈记录"

    report = f"""## 📊 投递反馈统计

- **总通知数**: {stats['total']}
- **已投递**: {stats['applied']}
- **不合适**: {stats['rejected']}
- **已查看**: {stats['viewed']}
- **待处理**: {stats['notified']}

### 按评分分布
- 90-100分: {stats['by_score_range']['90-100']} 个
- 80-89分: {stats['by_score_range']['80-89']} 个
- 70-79分: {stats['by_score_range']['70-79']} 个
- 0-69分: {stats['by_score_range']['0-69']} 个

### 投递率
- 投递率: {stats['applied'] / stats['total'] * 100:.1f}%
- 拒绝率: {stats['rejected'] / stats['total'] * 100:.1f}%
"""

    # 按公司统计（前5名）
    if stats["by_company"]:
        sorted_companies = sorted(stats["by_company"].items(), key=lambda x: x[1], reverse=True)[:5]
        report += "\n### 热门公司（前5）\n"
        for company, count in sorted_companies:
            report += f"- {company}: {count} 个岗位\n"

    return report


def get_dingtalk_webhook():
    """获取带签名的钉钉 Webhook URL"""
    if not DINGTALK_WEBHOOK:
        return None

    webhook_url = DINGTALK_WEBHOOK
    if DINGTALK_SECRET:
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{DINGTALK_SECRET}"
        hmac_code = hmac.new(
            DINGTALK_SECRET.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        separator = "&" if "?" in webhook_url else "?"
        webhook_url = f"{webhook_url}{separator}timestamp={timestamp}&sign={sign}"
    return webhook_url


def send_dingtalk(title, content):
    if not DINGTALK_WEBHOOK:
        print("[WARN] DINGTALK_WEBHOOK 未设置，跳过通知")
        return False

    try:
        from curl_cffi import requests as curl_requests
        use_curl = True
    except ImportError:
        import requests as std_requests
        use_curl = False

    webhook_url = get_dingtalk_webhook()

    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": content}
    }

    try:
        if use_curl:
            resp = curl_requests.post(webhook_url, json=payload, timeout=10)
        else:
            resp = std_requests.post(webhook_url, json=payload, timeout=10)
        result = resp.json()
        if result.get("errcode") == 0:
            print(f"[INFO] 钉钉通知发送成功: {title}")
            return True
        else:
            print(f"[ERROR] 钉钉通知失败: {result}")
            return False
    except Exception as e:
        print(f"[ERROR] 钉钉通知异常: {e}")
        return False


def send_dingtalk_actioncard(title, text, buttons):
    """发送 ActionCard 消息（带按钮）"""
    if not DINGTALK_WEBHOOK:
        print("[WARN] DINGTALK_WEBHOOK 未设置，跳过通知")
        return False

    try:
        from curl_cffi import requests as curl_requests
        use_curl = True
    except ImportError:
        import requests as std_requests
        use_curl = False

    webhook_url = get_dingtalk_webhook()

    payload = {
        "msgtype": "actionCard",
        "actionCard": {
            "title": title,
            "text": text,
            "btns": buttons
        }
    }

    try:
        if use_curl:
            resp = curl_requests.post(webhook_url, json=payload, timeout=10)
        else:
            resp = std_requests.post(webhook_url, json=payload, timeout=10)
        result = resp.json()
        if result.get("errcode") == 0:
            print(f"[INFO] 钉钉 ActionCard 发送成功: {title}")
            return True
        else:
            print(f"[ERROR] 钉钉 ActionCard 失败: {result}")
            return False
    except Exception as e:
        print(f"[ERROR] 钉钉 ActionCard 异常: {e}")
        return False


def make_job_id(job):
    key = f"{job.get('brandName', '')}-{job.get('jobName', '')}-{job.get('encryptJobId', '')}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def main():
    print("=" * 50)
    print(f"岗位抓取开始 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"抓取模式: {SCRAPE_MODE}")

    # 加载 profile.json
    load_profile()
    if PROFILE.get('score_threshold'):
        global SCORE_THRESHOLD
        SCORE_THRESHOLD = PROFILE['score_threshold']
        print(f"[INFO] 评分阈值: {SCORE_THRESHOLD}")

    try:
        from DrissionPage import ChromiumPage
        print("DrissionPage: 可用")
    except ImportError:
        print("DrissionPage: 未安装")

    try:
        from curl_cffi import requests as _
        print("curl_cffi: 可用 (Chrome TLS指纹)")
    except ImportError:
        print("curl_cffi: 未安装 (使用 requests)")

    print("=" * 50)

    seen = load_seen_jobs()
    new_jobs = []
    high_score_jobs = []
    total_queries = len(SEARCH_QUERIES)
    success_queries = 0
    total_raw_jobs = 0
    score_fail_count = 0

    for i, sq in enumerate(SEARCH_QUERIES):
        if COOKIE_ERROR:
            print(f"[WARN] 检测到Cookie错误，跳过剩余查询")
            break

        if i > 0:
            delay = random_delay(8, 18)
            print(f"[INFO] 查询间隔等待 {delay:.1f}s")

        platform = sq.get("platform", "boss")
        if platform == "liepin":
            jobs = search_liepin_jobs(sq["query"], sq["city"])
        elif platform == "lagou":
            jobs = search_lagou_jobs(sq["query"], sq["city"])
        elif platform == "niuke":
            jobs = search_niuke_jobs(sq["query"], sq["city"])
        elif platform == "zhaopin":
            jobs = search_zhaopin_jobs(sq["query"], sq["city"])
        elif platform == "shixiseng":
            jobs = search_shixiseng_jobs(sq["query"], sq["city"])
        else:
            jobs = search_boss_jobs(sq["query"], sq["city"])

        if jobs is not None:
            success_queries += 1
            total_raw_jobs += len(jobs)

        for job in jobs:
            job_id = make_job_id(job)
            if job_id in seen:
                continue

            job_name = job.get("jobName", "")
            company = job.get("brandName", "")
            salary = job.get("salaryDesc", "")
            location = job.get("areaDistrict", "")
            skills = ", ".join(job.get("skills", []))
            experience = job.get("jobExperience", "")
            boss_title = job.get("bossTitle", "")
            boss_online = job.get("bossOnline", False)
            encrypt_id = job.get("encryptJobId", "")
            url = job.get("url", f"https://www.zhipin.com/job_detail/{encrypt_id}.html")

            # 黑名单过滤
            is_blocked, block_keyword = check_blacklist(job_name, company, experience)
            if is_blocked:
                print(f"[SKIP] 黑名单过滤: {company} - {job_name} (命中: {block_keyword})")
                seen[job_id] = {"score": -1, "time": datetime.now().isoformat(), "blocked": block_keyword}
                continue

            jd_text = f"""职位: {job_name}
公司: {company}
经验: {experience}
薪资: {salary}
技能: {skills}
地点: {location}"""

            print(f"\n[评估] {company} - {job_name}")

            random_delay(2, 5)

            eval_result = evaluate_with_mimo(jd_text)
            score = eval_result.get("score", 0) if eval_result else 0
            reason = eval_result.get("reason", "") if eval_result else "评分失败"
            score_failed = eval_result is None
            if score_failed:
                score_fail_count += 1

            job_info = {
                "id": job_id,
                "company": company,
                "role": job_name,
                "salary": salary,
                "location": location,
                "skills": skills,
                "experience": experience,
                "boss_title": boss_title,
                "boss_online": boss_online,
                "url": url,
                "score": score,
                "reason": reason,
                "score_failed": score_failed,
                "time": datetime.now().isoformat(),
            }

            new_jobs.append(job_info)
            seen[job_id] = {"score": score, "time": datetime.now().isoformat()}

            if score_failed:
                print(f"  ⚠️ 评分失败，将直接推送岗位信息")
            elif score >= SCORE_THRESHOLD:
                high_score_jobs.append(job_info)
                print(f"  ✅ 高分! {score}/100 - {reason}")
            else:
                print(f"  ❌ 低分 {score}/100 - {reason}")

    save_seen_jobs(seen)

    print(f"\n{'=' * 50}")
    print(f"抓取完成: 查询 {success_queries}/{total_queries} 成功, 原始 {total_raw_jobs} 条, 新增 {len(new_jobs)} 条, 高分 {len(high_score_jobs)} 条")
    print(f"{'=' * 50}")

    if COOKIE_ERROR:
        send_dingtalk(
            "🚨 Cookie异常提醒",
            f"""## 🚨 Boss直聘 Cookie 异常

- **错误信息**: {COOKIE_ERROR}
- **发现时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}

### 处理步骤
1. 在浏览器中打开 [zhipin.com](https://www.zhipin.com) 登录
2. 完成安全验证（如有）
3. 运行 `python get_cookie.py` 更新 Cookie
4. 更新 GitHub Secrets 中的 `BOSS_COOKIE`

---
系统已暂停抓取，请尽快处理。"""
        )

    if new_jobs:
        for job in new_jobs:
            online_tag = " 🟢在线" if job["boss_online"] else ""
            if job.get("score_failed"):
                score_text = "评分失败"
            else:
                score_text = f"{job['score']}/100"

            # 生成跳转链接
            job_url = job['url']
            if 'zhipin.com' in job_url:
                # Boss直聘深链接，点击直接打开App
                action_link = f"[📱 立即沟通]({job_url.replace('https://www.zhipin.com/job_detail/', 'zhipin://platformapi/zhipin/chat?jobId=')})"
                view_link = f"[🌐 网页查看]({job_url})"
            else:
                action_link = f"[👉 立即投递]({job_url})"
                view_link = ""

            # 保存反馈记录
            save_feedback_record(job, action="notified")

            # 高分岗位使用 ActionCard 格式（带反馈按钮）
            if not job.get("score_failed") and job['score'] >= SCORE_THRESHOLD:
                msg = f"""## 📢 发现高分岗位

- **公司**: {job['company']}
- **职位**: {job['role']}
- **评分**: {score_text}
- **薪资**: {job['salary']}
- **地点**: {job['location']}
- **经验**: {job['experience']}
- **Boss**: {job['boss_title']}{online_tag}
- **理由**: {job['reason']}

{action_link}
{view_link}

---
请反馈您的处理结果："""

                job_id = make_job_id(job)
                buttons = [
                    {"title": "✅ 已投递", "actionURL": f"https://github.com/wuqiZhu/find_job/actions"},
                    {"title": "❌ 不合适", "actionURL": f"https://github.com/wuqiZhu/find_job/actions"},
                    {"title": "👀 已查看", "actionURL": f"https://github.com/wuqiZhu/find_job/actions"}
                ]
                send_dingtalk_actioncard(f"📢 {job['company']} - {job['role']}", msg, buttons)
            else:
                # 普通岗位使用 Markdown 格式
                msg = f"""## 📢 发现新岗位

- **公司**: {job['company']}
- **职位**: {job['role']}
- **评分**: {score_text}
- **薪资**: {job['salary']}
- **地点**: {job['location']}
- **经验**: {job['experience']}
- **Boss**: {job['boss_title']}{online_tag}
- **理由**: {job['reason']}

{action_link}
{view_link}

---
请及时查看并决定是否投递！"""
                send_dingtalk(f"📢 {job['company']} - {job['role']}", msg)

            time.sleep(1)

    high_score_list = ""
    for job in high_score_jobs:
        high_score_list += f"- [{job['score']}分] **{job['company']}** - {job['role']} ({job['salary']})\n"
    if not high_score_jobs:
        high_score_list = "本次无高分岗位\n"

    # 获取反馈统计
    feedback_stats = get_feedback_stats()
    feedback_summary = ""
    if feedback_stats["total"] > 0:
        feedback_summary = f"""
### 📈 投递反馈统计（累计）
- 总通知: {feedback_stats['total']} | 已投递: {feedback_stats['applied']} | 不合适: {feedback_stats['rejected']} | 待处理: {feedback_stats['notified']}
- 投递率: {feedback_stats['applied'] / feedback_stats['total'] * 100:.1f}%"""

    summary = f"""## 📊 岗位抓取报告

- **时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
- **查询状态**: {success_queries}/{total_queries} 成功
- **原始岗位**: {total_raw_jobs} 条
- **新增岗位**: {len(new_jobs)} 条
- **高分岗位**: {len(high_score_jobs)} 条 (≥{SCORE_THRESHOLD}分)
- **评分失败**: {score_fail_count} 条

### 高分岗位列表
{high_score_list}
{feedback_summary}"""

    print("\n" + summary)

    with open("data/latest_report.md", "w", encoding="utf-8") as f:
        f.write(summary)

    print("\n[INFO] 报告已保存到 data/latest_report.md")

    if not COOKIE_ERROR:
        status_emoji = "✅" if high_score_jobs else "📭"
        status_text = f"发现 {len(high_score_jobs)} 个高分岗位" if high_score_jobs else "暂无高分岗位"
        send_dingtalk(
            f"{status_emoji} 抓取报告 - {status_text}",
            summary
        )


if __name__ == "__main__":
    main()
