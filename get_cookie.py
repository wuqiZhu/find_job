"""
Boss直聘 Cookie 获取工具
需要先安装: pip install selenium webdriver-manager
"""

import json
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

def get_boss_cookie():
    print("=" * 50)
    print("Boss直聘 Cookie 获取工具")
    print("=" * 50)
    print()
    print("请按照以下步骤操作：")
    print("1. 浏览器会自动打开Boss直聘登录页面")
    print("2. 请手动登录（扫码或手机号）")
    print("3. 登录成功后，按回车键继续...")
    print()

    # 配置浏览器选项
    chrome_options = Options()
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--start-maximized")

    # 初始化浏览器
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"浏览器初始化失败: {e}")
        print()
        print("请先安装 Chrome 浏览器，然后重试")
        return None

    try:
        # 打开Boss直聘
        driver.get("https://www.zhipin.com")
        time.sleep(2)

        # 等待用户登录
        input("登录完成后，按回车键继续...")

        # 获取Cookie
        cookies = driver.get_cookies()

        # 转换为字符串格式
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])

        print()
        print("=" * 50)
        print("Cookie 获取成功！")
        print("=" * 50)
        print()
        print("Cookie 内容：")
        print(cookie_str[:100] + "...")
        print()

        # 保存到文件
        with open("cookie.txt", "w", encoding="utf-8") as f:
            f.write(cookie_str)
        print("Cookie 已保存到 cookie.txt")

        return cookie_str

    except Exception as e:
        print(f"获取Cookie失败: {e}")
        return None
    finally:
        driver.quit()


def update_env_file(cookie):
    env_path = ".env"
    if not os.path.exists(env_path):
        print("错误：.env 文件不存在")
        return

    with open(env_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 更新 BOSS_COOKIE
    lines = content.split("\n")
    new_lines = []
    found = False
    for line in lines:
        if line.startswith("BOSS_COOKIE="):
            new_lines.append(f"BOSS_COOKIE={cookie}")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"BOSS_COOKIE={cookie}")

    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines))

    print("Cookie 已更新到 .env 文件")


if __name__ == "__main__":
    cookie = get_boss_cookie()
    if cookie:
        update_env_file(cookie)
        print()
        print("现在可以运行脚本了：python scripts/github_scraper.py")
