import os
import sys
import json
import time
import random

try:
    from curl_cffi import requests as curl_requests
    USE_CURL_CFFI = True
except ImportError:
    import requests as std_requests
    USE_CURL_CFFI = False

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
cookie = ''
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip().startswith('BOSS_COOKIE='):
                cookie = line.strip().split('=', 1)[1]
                break

if not cookie:
    cookie = os.environ.get('BOSS_COOKIE', '')

url = 'https://www.zhipin.com/wapi/zpgeek/search/joblist.json'
headers_list = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.zhipin.com/web/geek/job",
        "Origin": "https://www.zhipin.com",
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
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
    },
]

queries = [
    ('嵌入式Linux开发', '101280600'),
    ('嵌入式Linux开发', '101020100'),
    ('BSP工程师', '101280600'),
    ('Linux驱动开发', '101280600'),
]

print(f"HTTP客户端: {'curl_cffi (Chrome TLS指纹)' if USE_CURL_CFFI else 'requests (标准库)'}")
if not cookie:
    print("[ERROR] 未找到 BOSS_COOKIE，请在 .env 文件或环境变量中设置")
    sys.exit(1)

for i, (query, city) in enumerate(queries):
    if i > 0:
        delay = random.uniform(8, 15)
        print(f"[INFO] 等待 {delay:.1f}s...")
        time.sleep(delay)

    params = {
        'scene': '1',
        'query': query,
        'city': city,
        'experience': '104,105,106',
        'page': 1,
        'pageSize': 30,
    }

    headers = random.choice(headers_list).copy()
    headers['Cookie'] = cookie

    try:
        if USE_CURL_CFFI:
            resp = curl_requests.get(url, headers=headers, params=params, timeout=20, impersonate="chrome131")
        else:
            resp = std_requests.get(url, headers=headers, params=params, timeout=20)

        data = resp.json()
        code = data.get('code')
        message = data.get('message', '')
        jobs = data.get('zpData', {}).get('jobList', [])
        print(f'[code={code}] query={query}, city={city}, jobs={len(jobs)}')

        if code == 1:
            print(f'  [WARN] 业务错误: {message}')
            if '登录' in message or '安全' in message or '验证' in message:
                print('  [ERROR] Cookie可能已失效，请更新BOSS_COOKIE')
                break
        elif code == 0 and not jobs:
            print(f'  [INFO] 无匹配结果')

    except Exception as e:
        print(f'[ERROR] query={query}, city={city}: {e}')
