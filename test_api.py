import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 50)
print("API Configuration Test")
print("=" * 50)

# Test MiMo API
print("\n1. Testing MiMo API...")
mimo_key = os.getenv('MIMO_API_KEY', '')
mimo_url = os.getenv('MIMO_BASE_URL', '')
mimo_model = os.getenv('MIMO_MODEL', '')

print(f"   API Key: {mimo_key[:10]}...")
print(f"   Base URL: {mimo_url}")
print(f"   Model: {mimo_model}")

try:
    url = f"{mimo_url}/chat/completions"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {mimo_key}'
    }
    payload = {
        'model': mimo_model,
        'messages': [{'role': 'user', 'content': 'Hello'}],
        'max_tokens': 5
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code == 200:
        print("   Status: OK")
    else:
        print(f"   Status: Failed ({resp.status_code})")
except Exception as e:
    print(f"   Error: {e}")

# Test Boss API
print("\n2. Testing Boss API...")
boss_cookie = os.getenv('BOSS_COOKIE', '')
print(f"   Cookie length: {len(boss_cookie)}")

try:
    url = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.zhipin.com/web/geek/job",
        "Cookie": boss_cookie,
    }
    params = {
        "scene": "1",
        "query": "Python",
        "city": "101020100",
        "page": 1,
        "pageSize": 10,
    }
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    data = resp.json()
    code = data.get('code')
    message = data.get('message', '')
    print(f"   Response code: {code}")
    print(f"   Message: {message}")
    if code == 0:
        jobs = data.get('zpData', {}).get('jobList', [])
        print(f"   Jobs found: {len(jobs)}")
    else:
        print("   Cookie may be invalid or expired")
except Exception as e:
    print(f"   Error: {e}")

print("\n" + "=" * 50)
