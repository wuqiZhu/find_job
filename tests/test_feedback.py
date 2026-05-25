"""反馈模块测试"""
import os
import json
import pytest
import tempfile
from unittest.mock import patch


@pytest.fixture
def temp_feedback_file(tmp_path):
    feedback_file = str(tmp_path / "feedback_records.json")
    with patch('job_scraper.feedback.FEEDBACK_FILE', feedback_file):
        with patch('job_scraper.feedback.DATA_DIR', str(tmp_path)):
            yield feedback_file


def test_make_job_id():
    from job_scraper.feedback import make_job_id
    job = {"brandName": "华为", "jobName": "嵌入式实习", "encryptJobId": "abc123"}
    job_id = make_job_id(job)
    assert isinstance(job_id, str)
    assert len(job_id) == 12


def test_make_job_id_deterministic():
    from job_scraper.feedback import make_job_id
    job = {"brandName": "华为", "jobName": "嵌入式实习", "encryptJobId": "abc123"}
    assert make_job_id(job) == make_job_id(job)


def test_make_job_id_different_for_different_jobs():
    from job_scraper.feedback import make_job_id
    job1 = {"brandName": "华为", "jobName": "嵌入式实习", "encryptJobId": "abc123"}
    job2 = {"brandName": "小米", "jobName": "BSP实习", "encryptJobId": "def456"}
    assert make_job_id(job1) != make_job_id(job2)


def test_save_and_get_feedback(temp_feedback_file):
    from job_scraper.feedback import save_feedback_record, get_feedback_stats
    job = {
        "brandName": "华为", "jobName": "嵌入式实习",
        "score": 85, "salaryDesc": "200/天", "areaDistrict": "深圳",
        "url": "https://example.com/job/1", "encryptJobId": "1"
    }
    assert save_feedback_record(job, "notified") is True
    stats = get_feedback_stats()
    assert stats["total"] == 1
    assert stats["notified"] == 1


def test_update_feedback(temp_feedback_file):
    from job_scraper.feedback import save_feedback_record, update_feedback_record, make_job_id, get_feedback_stats
    job = {
        "brandName": "华为", "jobName": "嵌入式实习",
        "score": 85, "salaryDesc": "200/天", "areaDistrict": "深圳",
        "url": "https://example.com/job/1", "encryptJobId": "1"
    }
    save_feedback_record(job, "notified")
    job_id = make_job_id(job)
    assert update_feedback_record(job_id, "applied") is True
    stats = get_feedback_stats()
    assert stats["applied"] == 1
    assert stats["notified"] == 0


def test_get_feedback_stats_empty(temp_feedback_file):
    from job_scraper.feedback import get_feedback_stats
    stats = get_feedback_stats()
    assert stats["total"] == 0


def test_generate_feedback_report_empty(temp_feedback_file):
    from job_scraper.feedback import generate_feedback_report
    report = generate_feedback_report()
    assert "暂无反馈记录" in report
