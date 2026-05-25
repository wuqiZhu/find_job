"""配置模块测试"""
import os
import pytest
from unittest.mock import patch


def test_get_config_returns_dict():
    from job_scraper.config import get_config, reload_config
    reload_config()
    config = get_config()
    assert isinstance(config, dict)
    assert 'deepseek_api_key' in config
    assert 'dingtalk_webhook' in config
    assert 'boss_cookie' in config
    assert 'profile' in config


def test_get_config_is_cached():
    from job_scraper.config import get_config
    c1 = get_config()
    c2 = get_config()
    assert c1 is c2


def test_reload_config_clears_cache():
    from job_scraper.config import get_config, reload_config
    c1 = get_config()
    c2 = reload_config()
    assert c1 is not c2


@patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test-key-123'})
def test_config_reads_env_vars():
    from job_scraper.config import reload_config
    config = reload_config()
    assert config['deepseek_api_key'] == 'test-key-123'
