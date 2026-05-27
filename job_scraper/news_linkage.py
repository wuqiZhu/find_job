#!/usr/bin/env python3
"""新闻→求职联动模块"""

import os
import json
import time
import requests
from datetime import datetime, timedelta

NOTIFICATION_CENTER_URL = os.environ.get('NOTIFICATION_CENTER_URL', 'http://188.166.249.182:5050')
DINGTALK_WEBHOOK = os.environ.get('DINGTALK_WEBHOOK', '')
DINGTALK_SECRET = os.environ.get('DINGTALK_SECRET', '')

# 求职相关关键词
JOB_RELATED_KEYWORDS = [
    '招聘', '校招', '社招', '实习', '内推', '面试',
    '嵌入式', 'Linux', '物联网', 'C++', '驱动',
    '华为', '大疆', '小米', 'OPPO', 'vivo', '中兴',
    '联发科', '瑞芯微', '全志科技', '紫光展锐',
    '比亚迪', '蔚来', '小鹏', '理想', '移远通信',
    '广和通', '涂鸦智能', '美的', '海尔'
]

def fetch_news_signals(hours=6):
    """从统一通知中心获取最近的新闻信号"""
    try:
        url = f"{NOTIFICATION_CENTER_URL}/api/signals"
        params = {
            'source': 'trendradar',
            'hours': hours,
            'limit': 50
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json().get('signals', [])
        print(f"[WARN] 获取新闻信号失败: HTTP {resp.status_code}")
        return []
    except Exception as e:
        print(f"[ERROR] 获取新闻信号异常: {e}")
        return []

def analyze_job_relevance(news_item):
    """分析新闻与求职的相关性"""
    title = news_item.get('title', '')
    content = news_item.get('content', '')
    keywords = news_item.get('keywords', [])
    
    text = f"{title} {content}"
    found_keywords = []
    
    for keyword in JOB_RELATED_KEYWORDS:
        if keyword in text or keyword in keywords:
            found_keywords.append(keyword)
    
    # 计算相关性分数
    score = min(len(found_keywords) * 10, 100)
    
    return {
        'score': score,
        'keywords': found_keywords,
        'is_job_related': score >= 30
    }

def format_job_news_message(news_items):
    """格式化求职相关新闻消息"""
    if not news_items:
        return None
    
    msg_parts = ["## 📰 求职相关新闻速递"]
    
    for idx, item in enumerate(news_items[:5], 1):
        relevance = item.get('relevance', {})
        score = relevance.get('score', 0)
        keywords = relevance.get('keywords', [])
        
        msg_parts.append(f"""
### {idx}. {item.get('title', '')}
📊 相关度: {score}%
🏷️ 关键词: {', '.join(keywords) if keywords else '无'}
🔗 [查看详情]({item.get('url', '#')})
📅 {item.get('time', '')}
""")
    
    msg_parts.append("\n💡 提示：以上新闻可能包含招聘信息或行业动态，建议关注！")
    
    return '\n'.join(msg_parts)

def send_job_news_notification(news_items):
    """发送求职相关新闻通知"""
    message = format_job_news_message(news_items)
    if not message:
        return False
    
    # 通过统一通知中心发送
    try:
        url = f"{NOTIFICATION_CENTER_URL}/api/send"
        payload = {
            "title": "🔥 求职相关新闻速递",
            "content": message,
            "priority": "normal",
            "source": "find_job_news_linkage",
            "channels": ["dingtalk"]
        }
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200 and resp.json().get("success"):
            print("[INFO] 求职新闻通知发送成功")
            return True
        print(f"[WARN] 发送通知失败: {resp.text}")
        return False
    except Exception as e:
        print(f"[ERROR] 发送通知异常: {e}")
        # 降级到直接发送钉钉
        return send_dingtalk_direct("🔥 求职相关新闻速递", message)

def send_dingtalk_direct(title, content):
    """直接发送钉钉通知（降级方案）"""
    if not DINGTALK_WEBHOOK:
        print("[WARN] DINGTALK_WEBHOOK 未设置")
        return False
    
    try:
        import hmac
        import hashlib
        import base64
        import urllib.parse
        
        timestamp = str(int(time.time() * 1000))
        secret = DINGTALK_SECRET
        
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        
        url = f"{DINGTALK_WEBHOOK}&timestamp={timestamp}&sign={sign}"
        
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": content
            }
        }
        
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"[ERROR] 直接发送钉钉失败: {e}")
        return False

def run_news_linkage():
    """运行新闻→求职联动"""
    print("[INFO] 启动新闻→求职联动...")
    
    # 获取最近6小时的新闻信号
    signals = fetch_news_signals(hours=6)
    print(f"[INFO] 获取到 {len(signals)} 条新闻信号")
    
    # 分析相关性
    job_related_news = []
    for signal in signals:
        relevance = analyze_job_relevance(signal)
        if relevance['is_job_related']:
            signal['relevance'] = relevance
            job_related_news.append(signal)
    
    print(f"[INFO] 发现 {len(job_related_news)} 条求职相关新闻")
    
    # 发送通知
    if job_related_news:
        send_job_news_notification(job_related_news)
        # 保存到本地
        save_news_records(job_related_news)
    else:
        print("[INFO] 暂无求职相关新闻")
    
    return job_related_news

def save_news_records(news_items):
    """保存新闻记录到本地"""
    news_file = os.path.join("data", "job_news_records.json")
    os.makedirs("data", exist_ok=True)
    
    try:
        records = []
        if os.path.exists(news_file):
            with open(news_file, "r", encoding="utf-8") as f:
                records = json.load(f)
        
        # 去重
        existing_urls = {item.get('url') for item in records}
        
        for item in news_items:
            if item.get('url') not in existing_urls:
                item['saved_at'] = datetime.now().isoformat()
                records.append(item)
        
        # 保留最近100条
        records = records[-100:]
        
        with open(news_file, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        
        print(f"[INFO] 已保存 {len(news_items)} 条新闻记录")
    except Exception as e:
        print(f"[ERROR] 保存新闻记录失败: {e}")

def get_job_news_stats():
    """获取新闻统计信息"""
    news_file = os.path.join("data", "job_news_records.json")
    
    if not os.path.exists(news_file):
        return {"total": 0, "today": 0, "weekly": 0}
    
    try:
        with open(news_file, "r", encoding="utf-8") as f:
            records = json.load(f)
        
        today = datetime.now().date()
        week_ago = today - timedelta(days=7)
        
        today_count = 0
        weekly_count = 0
        
        for record in records:
            saved_at = record.get('saved_at', '')
            if saved_at:
                try:
                    saved_date = datetime.fromisoformat(saved_at).date()
                    if saved_date == today:
                        today_count += 1
                    if saved_date >= week_ago:
                        weekly_count += 1
                except:
                    pass
        
        return {
            "total": len(records),
            "today": today_count,
            "weekly": weekly_count
        }
    except Exception as e:
        print(f"[ERROR] 获取新闻统计失败: {e}")
        return {"total": 0, "today": 0, "weekly": 0}

if __name__ == "__main__":
    news = run_news_linkage()
    stats = get_job_news_stats()
    print(f"新闻统计: 总计 {stats['total']} 条, 今日 {stats['today']} 条, 本周 {stats['weekly']} 条")
