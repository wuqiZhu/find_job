"""投递反馈追踪模块"""
import os
import json
import hashlib
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DATA_DIR = "data"
FEEDBACK_FILE = os.path.join(DATA_DIR, "feedback_records.json")


def make_job_id(job: dict) -> str:
    """生成岗位唯一ID"""
    key = f"{job.get('brandName', '')}-{job.get('jobName', '')}-{job.get('encryptJobId', '')}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def save_feedback_record(job: dict, action: str = "notified") -> bool:
    """保存岗位反馈记录"""
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        records = {}
        if os.path.exists(FEEDBACK_FILE):
            with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
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

        with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.warning("保存反馈记录失败: %s", e)
        return False


def update_feedback_record(job_id: str, action: str) -> bool:
    """更新岗位反馈状态"""
    try:
        records = {}
        if os.path.exists(FEEDBACK_FILE):
            with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
                records = json.load(f)

        if job_id in records:
            records[job_id]["action"] = action
            records[job_id]["updated_at"] = datetime.now().isoformat()

            with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            return True
    except Exception as e:
        logger.warning("更新反馈记录失败: %s", e)
    return False


def get_feedback_stats() -> dict:
    """获取反馈统计信息"""
    try:
        if not os.path.exists(FEEDBACK_FILE):
            return {"total": 0, "stats": {}}

        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
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

            company = record.get("company", "未知")
            stats["by_company"][company] = stats["by_company"].get(company, 0) + 1

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
        logger.warning("获取反馈统计失败: %s", e)
        return {"total": 0, "stats": {}}


def generate_feedback_report() -> str:
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

    if stats["by_company"]:
        sorted_companies = sorted(stats["by_company"].items(), key=lambda x: x[1], reverse=True)[:5]
        report += "\n### 热门公司（前5）\n"
        for company, count in sorted_companies:
            report += f"- {company}: {count} 个岗位\n"

    return report
