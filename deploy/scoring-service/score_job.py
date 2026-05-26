#!/usr/bin/env python3
import sys
import json
import os
import requests

def _load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '.env')
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

_load_env_file()

DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
DEEPSEEK_BASE_URL = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1')
DEEPSEEK_MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')
MAX_CALLS = int(os.environ.get('MAX_API_CALLS_PER_RUN', '30'))
_call_count = 0

PROFILE = {}


def load_profile():
    global PROFILE
    profile_path = os.environ.get('PROFILE_PATH', os.path.join(os.path.dirname(__file__), '..', '..', 'profile.json'))
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


def evaluate_job(jd_text, company="Unknown", role="Unknown"):
    global _call_count

    if not DEEPSEEK_API_KEY:
        return {"error": "DEEPSEEK_API_KEY 未设置", "success": False}

    if _call_count >= MAX_CALLS:
        return {"error": f"已达到 API 调用上限 ({MAX_CALLS})", "success": False}

    _call_count += 1

    # 加载 profile
    if not PROFILE:
        load_profile()

    url = f"{DEEPSEEK_BASE_URL}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
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
- 本科生，XX大学，XX专业
- 求职意向：XX开发实习生
- 熟练掌握XX，熟悉XX，了解XX
- 项目经验：XX项目
- 证书：XX"""

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
        "model": DEEPSEEK_MODEL,
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
            return {"error": "无法解析MiMo响应", "raw": str(result)[:500], "success": False}

        text = text.strip().replace("```json", "").replace("```", "").strip()
        parsed = json.loads(text)
        score = parsed.get("score", 0)

        return {
            "company": company,
            "role": role,
            "score": score,
            "reason": parsed.get("reason", ""),
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
