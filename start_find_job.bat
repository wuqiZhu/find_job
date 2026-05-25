@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m job_scraper.main >> "logs\find_job.log" 2>&1
