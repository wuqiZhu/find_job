"""求职自动化主入口"""
import os
import sys
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from job_scraper.config import get_config
from job_scraper.logger import get_logger
from job_scraper.constants import SEARCH_QUERIES, SCORE_THRESHOLD, DATA_FILE
from job_scraper.scoring import evaluate_job
from job_scraper.notifier import send_markdown, send_actioncard
from job_scraper.feedback import make_job_id, save_feedback_record, get_feedback_stats
from job_scraper.scrapers.base import COOKIE_ERROR, random_delay

logger = get_logger("main")


def check_blacklist(job_name: str, company: str, experience: str, profile: dict) -> tuple:
    blacklist = profile.get('blacklist_keywords', [])
    text = f"{job_name} {company} {experience}"
    for keyword in blacklist:
        if keyword in text:
            return True, keyword
    return False, None


def load_seen_jobs() -> dict:
    os.makedirs("data", exist_ok=True)
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_seen_jobs(seen: dict):
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)


def run():
    from job_scraper.scrapers import search_jobs

    config = get_config()
    profile = config.get('profile', {})

    score_threshold = profile.get('score_threshold', SCORE_THRESHOLD)

    logger.info("=" * 50)
    logger.info("岗位抓取开始 - %s", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    logger.info("抓取模式: %s", config.get('scrape_mode', 'auto'))

    try:
        from DrissionPage import ChromiumPage
        logger.info("DrissionPage: 可用")
    except ImportError:
        logger.warning("DrissionPage: 未安装")

    try:
        from curl_cffi import requests as _
        logger.info("curl_cffi: 可用 (Chrome TLS指纹)")
    except ImportError:
        logger.warning("curl_cffi: 未安装 (使用 requests)")

    logger.info("=" * 50)

    seen = load_seen_jobs()
    new_jobs = []
    high_score_jobs = []
    total_queries = len(SEARCH_QUERIES)
    success_queries = 0
    total_raw_jobs = 0
    score_fail_count = 0

    for i, sq in enumerate(SEARCH_QUERIES):
        if COOKIE_ERROR:
            logger.warning("检测到Cookie错误，跳过剩余查询")
            break

        if i > 0:
            delay = random_delay(8, 18)
            logger.info("查询间隔等待 %.1fs", delay)

        platform = sq.get("platform", "boss")
        query = sq["query"]
        city = sq["city"]

        jobs = search_jobs(platform, query, city)

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

            is_blocked, block_keyword = check_blacklist(job_name, company, experience, profile)
            if is_blocked:
                logger.info("[SKIP] 黑名单过滤: %s - %s (命中: %s)", company, job_name, block_keyword)
                seen[job_id] = {"score": -1, "time": datetime.now().isoformat(), "blocked": block_keyword}
                continue

            jd_text = f"""职位: {job_name}
公司: {company}
经验: {experience}
薪资: {salary}
技能: {skills}
地点: {location}"""

            logger.info("[评估] %s - %s", company, job_name)

            random_delay(2, 5)

            eval_result = evaluate_job(jd_text, profile)
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
                logger.warning("  评分失败，将直接推送岗位信息")
            elif score >= score_threshold:
                high_score_jobs.append(job_info)
                logger.info("  高分! %d/100 - %s", score, reason)
            else:
                logger.info("  低分 %d/100 - %s", score, reason)

    save_seen_jobs(seen)

    logger.info("=" * 50)
    logger.info("抓取完成: 查询 %d/%d 成功, 原始 %d 条, 新增 %d 条, 高分 %d 条",
                success_queries, total_queries, total_raw_jobs, len(new_jobs), len(high_score_jobs))
    logger.info("=" * 50)

    if COOKIE_ERROR:
        send_markdown(
            "Cookie异常提醒",
            f"""## 🚨 Boss直聘 Cookie 异常

- **错误信息**: {COOKIE_ERROR}
- **发现时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}

### 处理步骤
1. 在浏览器中打开 zhipin.com 登录
2. 完成安全验证（如有）
3. 运行 python get_cookie.py 更新 Cookie
4. 更新 GitHub Secrets 中的 BOSS_COOKIE

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

            job_url = job['url']
            if 'zhipin.com' in job_url:
                action_link = f"[📱 立即沟通]({job_url.replace('https://www.zhipin.com/job_detail/', 'zhipin://platformapi/zhipin/chat?jobId=')})"
                view_link = f"[🌐 网页查看]({job_url})"
            else:
                action_link = f"[👉 立即投递]({job_url})"
                view_link = ""

            save_feedback_record(job, action="notified")

            if not job.get("score_failed") and job['score'] >= score_threshold:
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

                buttons = [
                    {"title": "✅ 已投递", "actionURL": "https://github.com/wuqiZhu/find_job/actions"},
                    {"title": "❌ 不合适", "actionURL": "https://github.com/wuqiZhu/find_job/actions"},
                    {"title": "👀 已查看", "actionURL": "https://github.com/wuqiZhu/find_job/actions"}
                ]
                send_actioncard(f"{job['company']} - {job['role']}", msg, buttons)
            else:
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
                send_markdown(f"{job['company']} - {job['role']}", msg)

            time.sleep(1)

    high_score_list = ""
    for job in high_score_jobs:
        high_score_list += f"- [{job['score']}分] **{job['company']}** - {job['role']} ({job['salary']})\n"
    if not high_score_jobs:
        high_score_list = "本次无高分岗位\n"

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
- **高分岗位**: {len(high_score_jobs)} 条 (≥{score_threshold}分)
- **评分失败**: {score_fail_count} 条

### 高分岗位列表
{high_score_list}
{feedback_summary}"""

    logger.info(summary)

    os.makedirs("data", exist_ok=True)
    with open("data/latest_report.md", "w", encoding="utf-8") as f:
        f.write(summary)

    logger.info("报告已保存到 data/latest_report.md")

    if not COOKIE_ERROR:
        status_emoji = "✅" if high_score_jobs else "📭"
        status_text = f"发现 {len(high_score_jobs)} 个高分岗位" if high_score_jobs else "暂无高分岗位"
        send_markdown(
            f"{status_emoji} 抓取报告 - {status_text}",
            summary
        )


if __name__ == "__main__":
    run()
