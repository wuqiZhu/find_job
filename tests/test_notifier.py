"""通知模块测试"""
import pytest
from unittest.mock import patch, MagicMock


@patch('job_scraper.notifier.get_config')
def test_get_webhook_url_no_webhook(mock_get_config):
    from job_scraper.notifier import _get_webhook_url
    mock_get_config.return_value = {'dingtalk_webhook': '', 'dingtalk_secret': ''}
    assert _get_webhook_url() is None


@patch('job_scraper.notifier.get_config')
def test_get_webhook_url_with_webhook(mock_get_config):
    from job_scraper.notifier import _get_webhook_url
    mock_get_config.return_value = {
        'dingtalk_webhook': 'https://oapi.dingtalk.com/robot/send?access_token=test',
        'dingtalk_secret': ''
    }
    url = _get_webhook_url()
    assert url is not None
    assert 'access_token=test' in url


@patch('job_scraper.notifier.get_config')
def test_get_webhook_url_with_secret(mock_get_config):
    from job_scraper.notifier import _get_webhook_url
    mock_get_config.return_value = {
        'dingtalk_webhook': 'https://oapi.dingtalk.com/robot/send?access_token=test',
        'dingtalk_secret': 'SECtest'
    }
    url = _get_webhook_url()
    assert url is not None
    assert 'timestamp=' in url
    assert 'sign=' in url


@patch('job_scraper.notifier._post')
def test_send_markdown(mock_post):
    from job_scraper.notifier import send_markdown
    mock_post.return_value = True
    result = send_markdown("测试标题", "测试内容")
    assert result is True
    mock_post.assert_called_once()


@patch('job_scraper.notifier._post')
def test_send_actioncard(mock_post):
    from job_scraper.notifier import send_actioncard
    mock_post.return_value = True
    buttons = [{"title": "按钮1", "actionURL": "https://example.com"}]
    result = send_actioncard("测试标题", "测试内容", buttons)
    assert result is True
    mock_post.assert_called_once()
