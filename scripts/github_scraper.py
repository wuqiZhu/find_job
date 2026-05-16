#!/usr/bin/env python3
"""
GitHub Actions 定时岗位抓取脚本
- 从 Boss 直聘搜索岗位
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
import requests
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
MIMO_BASE_URL = os.environ.get('MIMO_BASE_URL', 'https://api.xiaomimimo.com/v1')
MIMO_MODEL = os.environ.get('MIMO_MODEL', 'mimo-v2.5-pro')

SEARCH_QUERIES = [
    {"query": "嵌入式Linux开发", "city": "101280600", "city_name": "深圳"},
    {"query": "嵌入式Linux开发", "city": "101020100", "city_name": "上海"},
    {"query": "BSP工程师", "city": "101280600", "city_name": "深圳"},
    {"query": "Linux驱动开发", "city": "101280600", "city_name": "深圳"},
]

SCORE_THRESHOLD = 80
DATA_FILE = "data/seen_jobs.json"


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


def search_boss_jobs(query, city, page=1, page_size=30):
    if not BOSS_COOKIE:
        print("[WARN] BOSS_COOKIE 未设置，跳过抓取")
        return []

    url = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.zhipin.com/web/geek/job",
        "Cookie": BOSS_COOKIE,
    }
    params = {
        "scene": "1",
        "query": query,
        "city": city,
        "experience": "104,105,106",
        "page": page,
        "pageSize": page_size,
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        data = resp.json()
        job_list = data.get("zpData", {}).get("jobList", [])
        print(f"[INFO] 搜索 '{query}' 城市={city}: 获取 {len(job_list)} 条")
        return job_list
    except Exception as e:
        print(f"[ERROR] 搜索失败: {e}")
        return []


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


def evaluate_with_mimo(jd_text):
    if not MIMO_API_KEY:
        print("[WARN] MIMO_API_KEY 未设置，跳过评分")
        return None

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

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        result = resp.json()
        text = extract_mimo_response_text(result)
        if not text:
            return None
        text = text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        print(f"[ERROR] MiMo 评分失败: {e}")
        return None


def send_dingtalk(title, content):
    if not DINGTALK_WEBHOOK:
        print("[WARN] DINGTALK_WEBHOOK 未设置，跳过通知")
        return False

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
        resp = requests.post(webhook_url, json=payload, timeout=10)
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
    print("=" * 50)

    seen = load_seen_jobs()
    new_jobs = []
    high_score_jobs = []

    for sq in SEARCH_QUERIES:
        jobs = search_boss_jobs(sq["query"], sq["city"])
        time.sleep(2)

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

            time.sleep(1)

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
