"""各平台抓取器注册"""
from .boss import search_boss_jobs
from .liepin import search_liepin_jobs
from .lagou import search_lagou_jobs
from .niuke import search_niuke_jobs
from .zhaopin import search_zhaopin_jobs
from .shixiseng import search_shixiseng_jobs

SCRAPER_MAP = {
    "boss": search_boss_jobs,
    "liepin": search_liepin_jobs,
    "lagou": search_lagou_jobs,
    "niuke": search_niuke_jobs,
    "zhaopin": search_zhaopin_jobs,
    "shixiseng": search_shixiseng_jobs,
}

__all__ = [
    'search_boss_jobs',
    'search_liepin_jobs',
    'search_lagou_jobs',
    'search_niuke_jobs',
    'search_zhaopin_jobs',
    'search_shixiseng_jobs',
    'SCRAPER_MAP',
    'search_jobs',
]


def search_jobs(platform: str, query: str, city: str, **kwargs) -> list:
    func = SCRAPER_MAP.get(platform)
    if not func:
        return []
    return func(query=query, city=city, **kwargs)
