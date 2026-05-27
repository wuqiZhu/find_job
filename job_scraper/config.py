"""统一配置管理模块"""
import os
import json
import logging

logger = logging.getLogger(__name__)

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_config_cache = None


def _load_env_file():
    env_path = os.path.join(_project_root, '.env')
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


def _load_profile() -> dict:
    profile_path = os.environ.get('PROFILE_PATH', os.path.join(_project_root, 'profile.json'))
    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("profile.json 未找到: %s", profile_path)
        return {}
    except json.JSONDecodeError as e:
        logger.error("profile.json 解析失败: %s", e)
        return {}


def get_config() -> dict:
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    _load_env_file()

    # 支持多种API配置方式
    # 优先使用 DEEPSEEK_* 环境变量，其次使用 OPENAI_* 环境变量
    api_key = os.environ.get('DEEPSEEK_API_KEY', '') or os.environ.get('OPENAI_API_KEY', '')
    base_url = os.environ.get('DEEPSEEK_BASE_URL', '') or os.environ.get('OPENAI_API_BASE', 'https://api.xiaomimimo.com/v1')
    model = os.environ.get('DEEPSEEK_MODEL', '') or os.environ.get('OPENAI_MODEL', 'mimo-v2-flash')

    # 如果base_url不包含路径，添加/v1
    if base_url and not base_url.endswith('/v1'):
        base_url = base_url.rstrip('/') + '/v1'

    _config_cache = {
        'boss_cookie': os.environ.get('BOSS_COOKIE', ''),
        'scrape_mode': os.environ.get('SCRAPE_MODE', 'auto'),
        'deepseek_api_key': api_key,
        'deepseek_base_url': base_url,
        'deepseek_model': model,
        'dingtalk_webhook': os.environ.get('DINGTALK_WEBHOOK', ''),
        'dingtalk_secret': os.environ.get('DINGTALK_SECRET', ''),
        'liepin_cookie': os.environ.get('LIEPIN_COOKIE', ''),
        'zhaopin_cookie': os.environ.get('ZHAOPIN_COOKIE', ''),
        'zhaopin_at': os.environ.get('ZHAOPIN_AT', ''),
        'zhaopin_rt': os.environ.get('ZHAOPIN_RT', ''),
        'profile': _load_profile(),
        'project_root': _project_root,
    }
    return _config_cache


def reload_config() -> dict:
    global _config_cache
    _config_cache = None
    return get_config()
