#!/usr/bin/env python3
import subprocess
import sys
import json
import re
import os

CAREER_OPS_DIR = os.environ.get('CAREER_OPS_DIR', '/opt/career-ops')


def evaluate_job(jd_text, company="Unknown", role="Unknown"):
    try:
        result = subprocess.run(
            ['node', 'gemini-eval.mjs', '--no-save', jd_text],
            capture_output=True,
            text=True,
            cwd=CAREER_OPS_DIR,
            timeout=120
        )
        output = result.stdout

        score_match = re.search(r'(?:Score|SCORE)[：:\s]*(\d+\.?\d*)', output)
        score = float(score_match.group(1)) if score_match else 0
        if score <= 5:
            score = round(score * 20, 1)

        return {
            "company": company,
            "role": role,
            "score": score,
            "output": output[:500],
            "success": True
        }
    except Exception as e:
        return {"error": str(e), "success": False}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 score_job.py <jd文本> [公司名] [职位名]")
        print("示例: python3 score_job.py \"嵌入式Linux开发，3年经验...\" \"华为\" \"嵌入式工程师\"")
        sys.exit(1)

    jd = sys.argv[1]
    company = sys.argv[2] if len(sys.argv) > 2 else "Unknown"
    role = sys.argv[3] if len(sys.argv) > 3 else "Unknown"

    print(f"正在评估: {company} - {role} ...")
    result = evaluate_job(jd, company, role)
    print(json.dumps(result, ensure_ascii=False, indent=2))
