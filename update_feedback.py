#!/usr/bin/env python3
"""
投递反馈更新工具
用于手动更新岗位的投递状态
"""

import json
import os
import sys
from datetime import datetime


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
FEEDBACK_FILE = os.path.join(DATA_DIR, "feedback_records.json")


def load_records():
    if not os.path.exists(FEEDBACK_FILE):
        return {}
    with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_records(records):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def list_records(action_filter=None):
    records = load_records()
    if not records:
        print("暂无反馈记录")
        return

    print("\n" + "=" * 60)
    print(f"{'ID':<15} {'公司':<15} {'职位':<20} {'评分':<6} {'状态':<10}")
    print("=" * 60)

    for job_id, record in records.items():
        action = record.get("action", "notified")
        if action_filter and action != action_filter:
            continue

        company = record.get("company", "未知")[:14]
        role = record.get("role", "未知")[:19]
        score = record.get("score", 0)
        action_text = {
            "notified": "待处理",
            "applied": "已投递",
            "rejected": "不合适",
            "viewed": "已查看"
        }.get(action, action)

        print(f"{job_id:<15} {company:<15} {role:<20} {score:<6} {action_text:<10}")

    print("=" * 60)


def update_record(job_id, action):
    records = load_records()
    if job_id not in records:
        print(f"未找到记录: {job_id}")
        return False

    records[job_id]["action"] = action
    records[job_id]["updated_at"] = datetime.now().isoformat()
    save_records(records)
    print(f"已更新 {job_id} -> {action}")
    return True


def show_stats():
    records = load_records()
    if not records:
        print("暂无反馈记录")
        return

    stats = {
        "total": len(records),
        "notified": 0,
        "applied": 0,
        "rejected": 0,
        "viewed": 0
    }

    for record in records.values():
        action = record.get("action", "notified")
        if action in stats:
            stats[action] += 1

    print("\n" + "=" * 40)
    print("📊 投递反馈统计")
    print("=" * 40)
    print(f"总通知数: {stats['total']}")
    print(f"已投递:   {stats['applied']}")
    print(f"不合适:   {stats['rejected']}")
    print(f"已查看:   {stats['viewed']}")
    print(f"待处理:   {stats['notified']}")
    print("-" * 40)
    if stats['total'] > 0:
        print(f"投递率:   {stats['applied'] / stats['total'] * 100:.1f}%")
    print("=" * 40)


def main():
    if len(sys.argv) < 2:
        print("""
📋 投递反馈更新工具

用法:
  python update_feedback.py list [状态]     # 列出记录（可选：notified/applied/rejected/viewed）
  python update_feedback.py update <ID> <状态>  # 更新状态
  python update_feedback.py stats           # 显示统计

状态说明:
  notified  - 待处理（默认）
  applied   - 已投递
  rejected  - 不合适
  viewed    - 已查看

示例:
  python update_feedback.py list
  python update_feedback.py list applied
  python update_feedback.py update abc123 applied
  python update_feedback.py stats
""")
        return

    command = sys.argv[1]

    if command == "list":
        action_filter = sys.argv[2] if len(sys.argv) > 2 else None
        list_records(action_filter)

    elif command == "update":
        if len(sys.argv) < 4:
            print("用法: python update_feedback.py update <ID> <状态>")
            return
        job_id = sys.argv[2]
        action = sys.argv[3]
        if action not in ["notified", "applied", "rejected", "viewed"]:
            print(f"无效状态: {action}，可选：notified/applied/rejected/viewed")
            return
        update_record(job_id, action)

    elif command == "stats":
        show_stats()

    else:
        print(f"未知命令: {command}")


if __name__ == "__main__":
    main()