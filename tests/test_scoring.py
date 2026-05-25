"""评分模块测试"""
import pytest
from unittest.mock import patch, MagicMock


def test_extract_response_text_choices():
    from job_scraper.scoring import _extract_response_text
    result = {"choices": [{"message": {"content": '{"score": 85}'}}]}
    assert _extract_response_text(result) == '{"score": 85}'


def test_extract_response_text_result_field():
    from job_scraper.scoring import _extract_response_text
    result = {"result": "some text"}
    assert _extract_response_text(result) == "some text"


def test_extract_response_text_none():
    from job_scraper.scoring import _extract_response_text
    result = {"unknown": "format"}
    assert _extract_response_text(result) is None


def test_build_prompt_with_profile():
    from job_scraper.scoring import _build_prompt
    profile = {
        "education": {"grade": "大三", "school": "测试大学", "major": "计算机"},
        "target": "嵌入式实习",
        "skills": {"languages": ["C", "Python"]},
        "projects": [{"name": "测试项目", "tech_stack": "C, Linux"}],
        "certificates": ["CET-6"],
        "scoring_standards": {"90-100": "完美匹配"},
    }
    prompt = _build_prompt(profile, "嵌入式开发实习")
    assert "测试大学" in prompt
    assert "嵌入式开发实习" in prompt
    assert "CET-6" in prompt


def test_build_prompt_without_profile():
    from job_scraper.scoring import _build_prompt
    prompt = _build_prompt(None, "测试岗位")
    assert "长春大学" in prompt
    assert "测试岗位" in prompt


@patch('job_scraper.scoring.get_config')
def test_evaluate_job_no_api_key(mock_get_config):
    from job_scraper.scoring import evaluate_job
    mock_get_config.return_value = {'deepseek_api_key': '', 'profile': {}}
    result = evaluate_job("测试岗位")
    assert result is None
