"""统一日志模块"""
import os
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

_initialized = False

LOG_FILE = os.environ.get("LOG_FILE", "data/logs/scraper.log")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")


def setup_logging():
    """配置日志系统"""
    global _initialized
    if _initialized:
        return
    _initialized = True

    Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )

    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            file_handler,
            logging.StreamHandler(),
        ],
    )


def get_logger(name: str) -> logging.Logger:
    """获取日志记录器"""
    setup_logging()
    return logging.getLogger(name)
