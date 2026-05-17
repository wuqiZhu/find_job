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

SEARCH_QUERIES = [
    {"query": "嵌入式Linux开发", "city": "101280600", "city_name": "深圳"},
    {"query": "嵌入式Linux开发", "city": "101020100", "city_name": "上海"},
    {"query": "BSP工程师", "city": "101280600", "city_name": "深圳"},
    {"query": "Linux驱动开发", "city": "101280600", "city_name": "深圳"},
]

SCORE_THRESHOLD = 80
DATA_FILE = "data/seen_jobs.json"


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
            return []

        if code == 1:
            print(f"[WARN] 浏览器模式: 业务错误 code=1 - {message}")
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
                return []

            if code == 1:
                print(f"[WARN] HTTP模式: 业务错误 code=1 - {message}")
                if "登录" in message or "安全" in message or "验证" in message:
                    print("[ERROR] Cookie可能已失效，请更新BOSS_COOKIE")
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

    prompt = f"""你是一个求职匹配评估专家。请根据以下简历信息和职位描述，给出0-100的匹配度评分。

## 我的背景
- 嵌入式Linux开发工程师，3年以上经验
- 熟悉ARM架构、BSP开发、设备驱动
- 精通C/C++，熟悉Yocto/Buildroot
- 有RTOS开发经验

## 评分标准
- 90-100: 完美匹配，必须投递
- 80-89: 高度匹配，建议投递
- 70-79: 一般匹配，可考虑
- 60以下: 不太匹配

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


def make_job_id(job):
    key = f"{job.get('brandName', '')}-{job.get('jobName', '')}-{job.get('encryptJobId', '')}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def main():
    print("=" * 50)
    print(f"岗位抓取开始 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"抓取模式: {SCRAPE_MODE}")

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

    for i, sq in enumerate(SEARCH_QUERIES):
        if i > 0:
            delay = random_delay(8, 18)
            print(f"[INFO] 查询间隔等待 {delay:.1f}s")

        jobs = search_boss_jobs(sq["query"], sq["city"])

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
            url = f"https://www.zhipin.com/job_detail/{encrypt_id}.html"

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
    print(f"抓取完成: 新增 {len(new_jobs)} 条, 高分 {len(high_score_jobs)} 条")
    print(f"{'=' * 50}")

    if new_jobs:
        for job in new_jobs:
            online_tag = " 🟢在线" if job["boss_online"] else ""
            if job.get("score_failed"):
                score_text = "评分失败"
            else:
                score_text = f"{job['score']}/100"

            msg = f"""## 📢 发现新岗位

- **公司**: {job['company']}
- **职位**: {job['role']}
- **评分**: {score_text}
- **薪资**: {job['salary']}
- **地点**: {job['location']}
- **经验**: {job['experience']}
- **Boss**: {job['boss_title']}{online_tag}
- **理由**: {job['reason']}

[👉 查看详情]({job['url']})

---
请及时查看并决定是否投递！"""

            send_dingtalk(f"📢 {job['company']} - {job['role']}", msg)
            time.sleep(1)

    summary = f"""## 📊 岗位抓取报告

- **时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
- **新增岗位**: {len(new_jobs)} 条
- **高分岗位**: {len(high_score_jobs)} 条 (≥{SCORE_THRESHOLD}分)

### 高分岗位列表
"""
    for job in high_score_jobs:
        summary += f"- [{job['score']}分] **{job['company']}** - {job['role']} ({job['salary']})\n"

    if not high_score_jobs:
        summary += "本次无高分岗位\n"

    print("\n" + summary)

    with open("data/latest_report.md", "w", encoding="utf-8") as f:
        f.write(summary)

    print("\n[INFO] 报告已保存到 data/latest_report.md")


if __name__ == "__main__":
    main()
