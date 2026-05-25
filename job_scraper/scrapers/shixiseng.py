import time
import urllib.parse
import logging

from .base import create_chrome_options, safe_quit_driver, random_delay

logger = logging.getLogger(__name__)


def search_shixiseng_jobs(query: str, city: str = "深圳", page: int = 1, page_size: int = 10) -> list:
    try:
        from DrissionPage import ChromiumPage
    except ImportError:
        logger.warning("DrissionPage 未安装，跳过实习僧抓取")
        return []

    co = create_chrome_options()
    driver = None

    try:
        driver = ChromiumPage(co)

        encoded_key = urllib.parse.quote(query)
        encoded_city = urllib.parse.quote(city)
        url = f"https://www.shixiseng.com/interns?k={encoded_key}&c={encoded_city}&p={page}"
        driver.get(url)
        random_delay(4, 7)

        job_items = driver.eles('css:.intern-list .list-item, css:.intern-wrap .item, css:[class*="intern"] .job-item, css:.position-list .item')

        if not job_items:
            job_items = driver.eles('css:a[href*="/intern/"]')

        normalized_jobs = []
        for item in job_items[:page_size]:
            try:
                title_el = item.ele('css:.title, css:a[class*="title"], css:h3, css:.job-name')
                company_el = item.ele('css:.company, css:a[class*="company"], css:.company-name')
                salary_el = item.ele('css:.salary, css:span[class*="salary"]')
                city_el = item.ele('css:.city, css:span[class*="city"], css:.location')

                job_title = title_el.text.strip() if title_el else ''
                company = company_el.text.strip() if company_el else ''
                salary = salary_el.text.strip() if salary_el else ''
                job_city = city_el.text.strip() if city_el else city

                link_el = item.ele('css:a[href*="/intern/"]')
                job_url = link_el.attr('href') if link_el else ''
                if job_url and not job_url.startswith('http'):
                    job_url = f"https://www.shixiseng.com{job_url}"

                job_id = ''
                if '/intern/' in job_url:
                    job_id = job_url.split('/intern/')[-1].split('?')[0].split('.')[0]

                if not job_title:
                    continue

                normalized = {
                    'jobName': job_title,
                    'brandName': company,
                    'salaryDesc': salary,
                    'areaDistrict': job_city,
                    'skills': [],
                    'jobExperience': '实习',
                    'bossTitle': '',
                    'bossOnline': False,
                    'encryptJobId': job_id,
                    'url': job_url,
                    'platform': 'shixiseng',
                }
                normalized_jobs.append(normalized)
            except Exception:
                continue

        logger.info("实习僧: 搜索 '%s' 城市=%s: 获取 %d 条", query, city, len(normalized_jobs))
        return normalized_jobs

    except Exception as e:
        logger.error("实习僧: 抓取异常: %s", e)
        return []
    finally:
        safe_quit_driver(driver)
