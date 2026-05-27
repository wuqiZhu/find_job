import json
import time
import urllib.parse
import logging
import requests

from .base import create_chrome_options, safe_quit_driver, random_delay

logger = logging.getLogger(__name__)


def search_lagou_jobs(query: str, city: str = "深圳", page: int = 1, page_size: int = 15) -> list:
    try:
        from DrissionPage import ChromiumPage
    except ImportError:
        logger.warning("DrissionPage 未安装，跳过拉勾抓取")
        return []

    co = create_chrome_options()
    driver = None

    try:
        driver = ChromiumPage(co)

        encoded_key = urllib.parse.quote(query)
        url = f"https://www.lagou.com/wn/zhaopin?kd={encoded_key}&city={urllib.parse.quote(city)}"
        driver.get(url)
        random_delay(4, 7)

        api_url = "https://www.lagou.com/jobs/v2/positionAjax.json"
        data = {
            "first": "true",
            "pn": str(page),
            "kd": query,
            "city": city,
        }

        # 获取cookies用于requests请求
        cookies_dict = {}
        for cookie in driver.cookies():
            cookies_dict[cookie['name']] = cookie['value']

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": url,
            "User-Agent": driver.user_agent
        }

        resp = requests.post(api_url, data=data, headers=headers, cookies=cookies_dict)
        time.sleep(2)

        try:
            result = resp.json()
        except Exception:
            logger.error("拉勾: JSON解析失败")
            return []

        code = result.get('code')
        if code != 0:
            logger.warning("拉勾: code=%s", code)
            return []

        content = result.get('content', {})
        results = content.get('result', [])

        normalized_jobs = []
        for job in results:
            company = job.get('companyFullName', '')
            position = job.get('positionName', '')
            salary = job.get('salary', '')
            job_city = job.get('city', '')
            district = job.get('district', '')
            experience = job.get('workYear', '')
            position_id = job.get('positionId', '')

            skills = []
            if job.get('skillLables'):
                skills = job['skillLables']
            elif job.get('industryLables'):
                skills = job['industryLables']

            normalized = {
                'jobName': position,
                'brandName': company,
                'salaryDesc': salary,
                'areaDistrict': f"{job_city} {district}".strip(),
                'skills': skills,
                'jobExperience': experience,
                'bossTitle': '',
                'bossOnline': False,
                'encryptJobId': str(position_id),
                'url': f"https://www.lagou.com/wn/jobs/{position_id}.html",
                'platform': 'lagou',
            }
            normalized_jobs.append(normalized)

        logger.info("拉勾: 搜索 '%s' 城市=%s: 获取 %d 条", query, city, len(normalized_jobs))
        return normalized_jobs

    except Exception as e:
        logger.error("拉勾: 抓取异常: %s", e)
        return []
    finally:
        safe_quit_driver(driver)
