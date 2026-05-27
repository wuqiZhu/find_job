import json
import time
import urllib.parse
import logging
import requests

from ..config import get_config
from .base import create_chrome_options, safe_quit_driver, random_delay

logger = logging.getLogger(__name__)


def search_liepin_jobs(query: str, city: str = "040", page: int = 1, page_size: int = 20) -> list:
    config = get_config()
    liepin_cookie = config.get('liepin_cookie', '')

    if not liepin_cookie:
        logger.warning("LIEPIN_COOKIE 未设置，跳过猎聘抓取")
        return []

    try:
        from DrissionPage import ChromiumPage
    except ImportError:
        logger.warning("DrissionPage 未安装，跳过猎聘抓取")
        return []

    co = create_chrome_options()
    driver = None

    try:
        driver = ChromiumPage(co)

        driver.get("https://www.liepin.com")
        time.sleep(2)

        for item in liepin_cookie.split(';'):
            item = item.strip()
            if '=' in item:
                name, value = item.split('=', 1)
                try:
                    driver.set.cookies({"name": name.strip(), "value": value.strip(), "domain": ".liepin.com", "path": "/"})
                except Exception:
                    pass
        time.sleep(1)

        encoded_key = urllib.parse.quote(query)
        url = f"https://www.liepin.com/zhaopin/?key={encoded_key}&dq={city}"
        driver.get(url)
        random_delay(3, 6)

        api_url = "https://api-c.liepin.com/api/com.liepin.searchfront4c.pc-search-job"
        payload = {
            "data": {
                "mainSearchPc": {
                    "pcSearchForm": {
                        "city": city,
                        "dq": city,
                        "currentPage": page - 1,
                        "pageSize": page_size,
                        "key": query,
                        "workYearCode": "0,1,2,3",
                        "searchType": 1,
                        "scene": "input",
                        "sfrom": "search_job_pc",
                    }
                }
            }
        }

        # 获取cookies用于requests请求
        cookies_dict = {}
        for cookie in driver.cookies():
            cookies_dict[cookie['name']] = cookie['value']

        headers = {
            "Content-Type": "application/json",
            "Referer": url,
            "User-Agent": driver.user_agent
        }

        resp = requests.post(api_url, json=payload, headers=headers, cookies=cookies_dict)
        time.sleep(2)

        try:
            data = resp.json()
        except Exception:
            logger.error("猎聘: JSON解析失败")
            return []

        code = data.get('code')
        msg = data.get('msg', '')

        if str(code) != '0':
            logger.warning("猎聘: code=%s, msg=%s", code, msg)
            return []

        result = data.get('data', {})
        job_list = result.get('list', [])

        normalized_jobs = []
        for job in job_list:
            job_info = job.get('job', {})
            comp_info = job.get('comp', {})

            normalized = {
                'jobName': job_info.get('title', ''),
                'brandName': comp_info.get('compName', ''),
                'salaryDesc': job_info.get('salary', ''),
                'areaDistrict': job_info.get('dq', ''),
                'skills': job_info.get('labels', []),
                'jobExperience': job_info.get('workYear', ''),
                'bossTitle': '',
                'bossOnline': False,
                'encryptJobId': job_info.get('jobId', ''),
                'url': f"https://www.liepin.com/job/{job_info.get('jobId', '')}.shtml",
                'platform': 'liepin',
            }
            normalized_jobs.append(normalized)

        logger.info("猎聘: 搜索 '%s' 城市=%s: 获取 %d 条", query, city, len(normalized_jobs))
        return normalized_jobs

    except Exception as e:
        logger.error("猎聘: 抓取异常: %s", e)
        return []
    finally:
        safe_quit_driver(driver)
