"""AI岗位匹配评分模块"""
import json
import os
import logging
from .config import get_config

logger = logging.getLogger(__name__)


def _extract_response_text(result: dict) -> str:
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

    logger.warning("无法解析AI响应: %s", json.dumps(result, ensure_ascii=False)[:500])
    return None


def _build_prompt(profile: dict, jd_text: str) -> str:
    if profile:
        edu = profile.get('education', {})
        skills = profile.get('skills', {})
        projects = profile.get('projects', [])
        certificates = profile.get('certificates', [])
        standards = profile.get('scoring_standards', {})

        skill_lines = []
        for category, items in skills.items():
            skill_lines.extend([f"- {item}" for item in items])

        project_lines = [f"- {p['name']}（{p['tech_stack']}）" for p in projects]
        standard_lines = [f"- {score}: {desc}" for score, desc in standards.items()]

        background = f"""## 我的背景
- {edu.get('grade', '')}，{edu.get('school', '')}，{edu.get('major', '')}专业
- 求职意向：{profile.get('target', '')}
{chr(10).join(skill_lines)}
- 项目经验：{', '.join([p['name'] for p in projects])}
- {', '.join(certificates)}"""

        scoring_standards = f"""## 评分标准（重要：我是找实习的在校大学生，应该广撒网，多投递！）
{chr(10).join(standard_lines)}

**评分原则**：
1. 只要是嵌入式、Linux、物联网、C/C++、单片机等相关领域，最低给60分
2. 有"实习"关键词的岗位，额外加10分
3. 技能可以学习，不要因为某个技能不熟悉就大幅扣分
4. 宁可多投，不要漏投！"""
    else:
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

    return f"""你是一个求职匹配评估专家。请根据以下简历信息和职位描述，给出0-100的匹配度评分。

{background}

{scoring_standards}

## 职位描述
{jd_text}

请只返回一个JSON格式：{{"score": 分数, "reason": "简短理由"}}
"""


def evaluate_job(jd_text: str, profile: dict = None, max_retries: int = 2) -> dict:
    try:
        from curl_cffi import requests as curl_requests
        use_curl = True
    except ImportError:
        import requests as std_requests
        use_curl = False

    config = get_config()
    api_key = config.get('deepseek_api_key', '')
    if not api_key:
        logger.warning("DEEPSEEK_API_KEY 未设置，跳过评分")
        return None

    if profile is None:
        profile = config.get('profile', {})

    url = f"{config.get('deepseek_base_url', 'https://api.deepseek.com/v1')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    prompt = _build_prompt(profile, jd_text)

    payload = {
        "model": config.get('deepseek_model', 'deepseek-chat'),
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
                import time
                wait = (attempt + 1) * 5
                logger.warning("DeepSeek API限流，等待 %ds", wait)
                time.sleep(wait)
                continue

            if resp.status_code != 200:
                logger.error("DeepSeek API返回 HTTP %d: %s", resp.status_code, resp.text[:200])
                if attempt < max_retries - 1:
                    import time
                    time.sleep(3)
                continue

            result = resp.json()
            text = _extract_response_text(result)
            if not text:
                return None
            text = text.strip().replace("```json", "").replace("```", "").strip()
            parsed = json.loads(text)
            return {"score": parsed.get("score", 0), "reason": parsed.get("reason", "")}

        except json.JSONDecodeError as e:
            logger.error("评分响应解析失败 (尝试 %d/%d): %s", attempt + 1, max_retries, e)
            if attempt < max_retries - 1:
                import time
                time.sleep(3)
        except Exception as e:
            logger.error("评分失败 (尝试 %d/%d): %s", attempt + 1, max_retries, e)
            if attempt < max_retries - 1:
                import time
                time.sleep(3)

    return None
