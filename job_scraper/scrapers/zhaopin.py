import json
import time
import logging

from ..config import get_config

logger = logging.getLogger(__name__)


def search_zhaopin_jobs(query: str, city: str = "763", page: int = 1, page_size: int = 20) -> list:
    config = get_config()
    zhaopin_cookie = config.get('zhaopin_cookie', '')
    zhaopin_at = config.get('zhaopin_at', '')
    zhaopin_rt = config.get('zhaopin_rt', '')

    if not zhaopin_cookie:
        logger.warning("ZHAOPIN_COOKIE 未设置，跳过智联抓取")
        return []

    try:
        from curl_cffi import requests as curl_requests
        use_curl = True
    except ImportError:
        import requests as std_requests
        use_curl = False

    url = "https://fe-api.zhaopin.com/c/i/sou"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://sou.zhaopin.com/",
        "Origin": "https://www.zhaopin.com",
        "Cookie": zhaopin_cookie,
    }

    params = {
        "pageSize": str(page_size),
        "cityId": city,
        "workExperience": "-1",
        "education": "-1",
        "companyType": "-1",
        "employmentType": "-1",
        "jobWelfareTag": "-1",
        "kw": query,
        "kt": "3",
    }

    if zhaopin_at:
        params["at"] = zhaopin_at
    if zhaopin_rt:
        params["rt"] = zhaopin_rt

    for attempt in range(3):
        try:
            if use_curl:
                resp = curl_requests.get(url, headers=headers, params=params, timeout=20, impersonate="chrome131")
            else:
                resp = std_requests.get(url, headers=headers, params=params, timeout=20)

            if resp.status_code != 200:
                logger.warning("智联: HTTP %d (尝试 %d/3)", resp.status_code, attempt + 1)
                time.sleep(5)
                continue

            data = resp.json()
            code = data.get('code')

            if code != 200:
                logger.warning("智联: code=%s (尝试 %d/3)", code, attempt + 1)
                time.sleep(5)
                continue

            result = data.get('data', {})
            job_list = result.get('list', result.get('results', []))

            normalized_jobs = []
            for job in job_list:
                job_name = job.get('jobName', '')
                company_info = job.get('company', {})
                company_name = company_info.get('name', '')
                salary = job.get('salary', '')
                city_name = job.get('city', {}).get('display', '') if isinstance(job.get('city'), dict) else str(job.get('city', ''))
                job_number = job.get('number', '')
                work_exp = job.get('workExp', {}).get('display', '') if isinstance(job.get('workExp'), dict) else str(job.get('workExp', ''))

                job_url = f"https://jobs.zhaopin.com/{job_number}.htm"

                normalized = {
                    'jobName': job_name,
                    'brandName': company_name,
                    'salaryDesc': salary,
                    'areaDistrict': city_name,
                    'skills': [],
                    'jobExperience': work_exp,
                    'bossTitle': '',
                    'bossOnline': False,
                    'encryptJobId': job_number,
                    'url': job_url,
                    'platform': 'zhaopin',
                }
                normalized_jobs.append(normalized)

            logger.info("智联: 搜索 '%s' 城市=%s: 获取 %d 条", query, city, len(normalized_jobs))
            return normalized_jobs

        except json.JSONDecodeError:
            logger.warning("智联: JSON解析失败 (尝试 %d/3)", attempt + 1)
            time.sleep(5)
        except Exception as e:
            logger.error("智联: 请求失败 (尝试 %d/3): %s", attempt + 1, e)
            time.sleep(5)

    logger.error("智联: 3次重试均失败")
    return []
