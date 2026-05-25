import time
import urllib.parse
import logging

from .base import create_chrome_options, safe_quit_driver, random_delay

logger = logging.getLogger(__name__)


def search_niuke_jobs(query: str, city: str = "深圳", page: int = 1, page_size: int = 20) -> list:
    try:
        from DrissionPage import ChromiumPage
    except ImportError:
        logger.warning("DrissionPage 未安装，跳过牛客抓取")
        return []

    co = create_chrome_options()
    driver = None

    try:
        driver = ChromiumPage(co)

        encoded_key = urllib.parse.quote(query)
        url = f"https://www.nowcoder.com/search/all?query={encoded_key}&type=job"
        driver.get(url)
        random_delay(4, 7)

        job_items = driver.eles('css:.search-job-result .job-list-item, css:.nc-job-list .job-item, css:[class*="job"] .item, css:.search-result-list .result-item')

        if not job_items:
            job_items = driver.eles('css:a[href*="/job/"]')

        normalized_jobs = []
        for item in job_items[:page_size]:
            try:
                title_el = item.ele('css:.job-name, css:.position-name, css:h3, css:a[class*="title"]')
                company_el = item.ele('css:.company-name, css:.company, css:span[class*="company"]')
                salary_el = item.ele('css:.salary, css:span[class*="salary"]')
                location_el = item.ele('css:.location, css:span[class*="location"], css:.city')

                job_title = title_el.text.strip() if title_el else ''
                company = company_el.text.strip() if company_el else ''
                salary = salary_el.text.strip() if salary_el else ''
                location = location_el.text.strip() if location_el else city

                link_el = item.ele('css:a[href*="/job/"]')
                job_url = link_el.attr('href') if link_el else ''
                if job_url and not job_url.startswith('http'):
                    job_url = f"https://www.nowcoder.com{job_url}"

                job_id = ''
                if '/job/' in job_url:
                    job_id = job_url.split('/job/')[-1].split('?')[0].split('.')[0]

                if not job_title:
                    continue

                normalized = {
                    'jobName': job_title,
                    'brandName': company,
                    'salaryDesc': salary,
                    'areaDistrict': location,
                    'skills': [],
                    'jobExperience': '',
                    'bossTitle': '',
                    'bossOnline': False,
                    'encryptJobId': job_id,
                    'url': job_url,
                    'platform': 'niuke',
                }
                normalized_jobs.append(normalized)
            except Exception:
                continue

        logger.info("牛客: 搜索 '%s' 城市=%s: 获取 %d 条", query, city, len(normalized_jobs))
        return normalized_jobs

    except Exception as e:
        logger.error("牛客: 抓取异常: %s", e)
        return []
    finally:
        safe_quit_driver(driver)
