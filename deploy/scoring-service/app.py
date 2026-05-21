import json
import os
import logging
import requests
from datetime import datetime
from flask import Flask, request, jsonify

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', 'sk-97d3644395eb4087b2137c0073f65697')
DEEPSEEK_BASE_URL = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1')
DEEPSEEK_MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')

PROFILE = {}


def load_profile():
    global PROFILE
    profile_path = os.environ.get('PROFILE_PATH', os.path.join(os.path.dirname(__file__), '..', '..', 'profile.json'))
    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            PROFILE = json.load(f)
            logger.info(f"已加载 profile.json")
            return PROFILE
    except FileNotFoundError:
        logger.warning("profile.json 未找到，使用默认配置")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"profile.json 解析失败: {e}")
        return {}


# 启动时加载 profile
load_profile()


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

    logger.warning(f"无法解析DeepSeek响应，原始响应: {json.dumps(result, ensure_ascii=False)[:500]}")
    return None


def evaluate_with_deepseek(jd_text):
    if not DEEPSEEK_API_KEY:
        return {"error": "DEEPSEEK_API_KEY 未设置", "success": False}

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
            "score": score,
            "reason": parsed.get("reason", ""),
            "success": True
        }
    except Exception as e:
        return {"error": str(e), "success": False}


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.utcnow().isoformat()})


@app.route('/evaluate', methods=['POST'])
def evaluate():
    data = request.get_json(force=True, silent=True)
    if not data or 'jd' not in data:
        return jsonify({'error': 'Missing "jd" field in request body'}), 400

    jd_text = data['jd']
    company = data.get('company', 'Unknown')
    role = data.get('role', 'Unknown')

    if not jd_text.strip():
        return jsonify({'error': 'Empty "jd" field'}), 400

    logger.info(f"Evaluating: {company} - {role}")

    try:
        result = evaluate_with_deepseek(jd_text)

        if not result.get('success'):
            logger.warning(f"Evaluation failed: {company} - {role}: {result.get('error')}")
            return jsonify({
                'company': company,
                'role': role,
                'score': 0,
                'error': result.get('error', '评分失败'),
                'success': False
            })

        score = result.get('score', 0)

        response = {
            'company': company,
            'role': role,
            'score': score,
            'reason': result.get('reason', ''),
            'success': True
        }

        logger.info(f"Result: {company} - {role} => score={score}")
        return jsonify(response)

    except Exception as e:
        logger.error(f"Error evaluating {company} - {role}: {e}")
        return jsonify({'error': str(e), 'success': False}), 500


@app.route('/evaluate-batch', methods=['POST'])
def evaluate_batch():
    data = request.get_json(force=True, silent=True)
    if not data or 'jobs' not in data:
        return jsonify({'error': 'Missing "jobs" field'}), 400

    jobs = data['jobs']
    if len(jobs) > 10:
        return jsonify({'error': 'Max 10 jobs per batch'}), 400

    results = []
    for job in jobs:
        jd = job.get('jd', '')
        company = job.get('company', 'Unknown')
        role = job.get('role', 'Unknown')

        if not jd.strip():
            results.append({'company': company, 'role': role, 'error': 'Empty JD', 'success': False})
            continue

        try:
            result = evaluate_with_deepseek(jd)

            if not result.get('success'):
                results.append({
                    'company': company,
                    'role': role,
                    'error': result.get('error', '评分失败'),
                    'success': False
                })
            else:
                results.append({
                    'company': company,
                    'role': role,
                    'score': result.get('score', 0),
                    'reason': result.get('reason', ''),
                    'success': True
                })
        except Exception as e:
            results.append({'company': company, 'role': role, 'error': str(e), 'success': False})

    success_count = sum(1 for r in results if r.get('success'))
    logger.info(f"Batch complete: {success_count}/{len(jobs)} successful")
    return jsonify({'results': results, 'total': len(jobs), 'success': success_count})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting scoring service on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
