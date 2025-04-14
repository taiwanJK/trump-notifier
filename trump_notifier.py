import subprocess
import json
import time
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os

# 引入 googletrans 與 LibreTranslate
from googletrans import Translator
from libretranslatepy import LibreTranslateAPI
google_translator = Translator(service_urls=['translate.google.com'])
libre_translator = LibreTranslateAPI("https://translate.flossboxin.org.in/")

# 載入環境變數
from dotenv import load_dotenv
load_dotenv()

# 取得環境變數
TRUTHSOCIAL_SEARCH_USERNAME = os.environ.get("TRUTHSOCIAL_SEARCH_USERNAME", "realDonaldTrump")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
CHECK_INTERVAL = 600  # 每 600 秒（10 分鐘）檢查一次
SEEN_IDS_FILE = Path('seen_post_ids.txt')

# --- 1. 傳送 Telegram 訊息函數 ---
def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    response = requests.post(url, json=payload)
    return response.status_code == 200

# --- 2. 讀取已通知過的貼文 ID ---
def load_seen_ids():
    if SEEN_IDS_FILE.exists():
        with open(SEEN_IDS_FILE, 'r') as f:
            return set(line.strip() for line in f)
    return set()

# --- 3. 儲存已通知的貼文 ID ---
def save_seen_ids(seen_ids):
    with open(SEEN_IDS_FILE, 'w') as f:
        for pid in seen_ids:
            f.write(pid + '\n')

# --- 4. 使用 truthbrush 抓取川普貼文
def fetch_trump_posts():
    # 取得當下 UTC 時間往前 15 分鐘作為篩選時間
    ten_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=15)
    since = ten_minutes_ago.isoformat()

    print(f"🔍 抓取從 {since} 之後的貼文...")

    try:
        result = subprocess.run(
            ["truthbrush", "statuses", TRUTHSOCIAL_SEARCH_USERNAME, "--no-replies", "--created-after", since],
            capture_output=True,
            text=True
        )
        return [json.loads(line) for line in result.stdout.strip().splitlines() if line.strip()]
    except Exception as e:
        print("Error fetching posts:", e)
        return []

# --- 5. 將 HTML 貼文轉成純文字 ---
def extract_post_text(post):
    # 處理 HTML content
    from html import unescape
    import re
    content_html = post.get("content", "")
    content_text = re.sub(r"<[^>]*>", "", content_html)
    return unescape(content_text.strip())

# --- 6. 使用 googletrans或libretranslatepy 翻譯英文為中文 ---
def translate_to_chinese(text, retries=2):
    # 先試 googletrans
    for attempt in range(retries):
        try:
            result = google_translator.translate(text, dest='zh-tw')
            if result and result.text:
                return result.text
        except Exception as e:
            print(f"⚠️ googletrans 第 {attempt + 1} 次翻譯失敗: {e}")
            time.sleep(5)

    # 改用 LibreTranslate fallback
    try:
        print("🔁 使用 LibreTranslate fallback 翻譯中...")
        return libre_translator.translate(text, source="en", target="zh")
    except Exception as e:
        print("❌ LibreTranslate 翻譯也失敗:", e)
        return "[翻譯失敗]"

# --- 7. 主程式邏輯 ---
def main():
    print("🟢 Trump notifier started.")
    seen_ids = load_seen_ids()

    # 過濾出尚未通知的新貼文（以貼文 ID 作為唯一識別）
    while True:
        posts = fetch_trump_posts()
        new_posts = []

        for post in posts:
            post_id = post["id"]
            if post_id not in seen_ids:
                new_posts.append(post)
                seen_ids.add(post_id)

        if new_posts:
            print(f"📢 推送 {len(new_posts)} 篇新貼文")

            # 按發文時間排序，舊的先通知
            for post in sorted(new_posts, key=lambda x: x["created_at"]):
                display_name = post["account"]["display_name"]
                text = extract_post_text(post)
                url = post["url"]
                media = post.get("media_attachments", [])
                media_note = "\n🎥 <i>含有影片</i>" if any(m['type'] == 'video' for m in media) else ""
                # 呼叫翻譯函數
                translated = translate_to_chinese(text)
                msg = f"<b>{display_name} 發文：</b>\n{text}\n\n<b>翻譯：</b>\n{translated}\n🔗 {url}{media_note}"
                send_telegram_message(msg)

            # 更新已通知清單
            save_seen_ids(seen_ids)
        else:
            print("🕒 無新貼文")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()