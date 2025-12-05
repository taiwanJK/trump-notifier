import subprocess
import json
import time
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import base64

# 載入環境變數
from dotenv import load_dotenv
load_dotenv(override=True)

# 取得環境變數
TRUTHSOCIAL_SEARCH_USERNAME = os.environ.get("TRUTHSOCIAL_SEARCH_USERNAME", "realDonaldTrump")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
CHECK_INTERVAL = 600  # 每 600 秒（10 分鐘）檢查一次
SEEN_IDS_FILE = Path('seen_post_ids.txt')
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# 代理設定
HTTP_PROXY_ENABLED = os.environ.get("HTTP_PROXY_ENABLED", "false").lower() == "true"
HTTP_PROXY_HOST = os.environ.get("HTTP_PROXY_HOST", "")
HTTP_PROXY_PORT = os.environ.get("HTTP_PROXY_PORT", "")
HTTP_PROXY_USERNAME = os.environ.get("HTTP_PROXY_USERNAME", "")
HTTP_PROXY_PASSWORD = os.environ.get("HTTP_PROXY_PASSWORD", "")

# 設定代理
proxies = {}
if HTTP_PROXY_ENABLED and HTTP_PROXY_HOST and HTTP_PROXY_PORT:
    proxy_auth = ""
    if HTTP_PROXY_USERNAME and HTTP_PROXY_PASSWORD:
        proxy_auth = f"{HTTP_PROXY_USERNAME}:{HTTP_PROXY_PASSWORD}@"
    
    proxy_url = f"http://{proxy_auth}{HTTP_PROXY_HOST}:{HTTP_PROXY_PORT}"
    proxies = {
        "http": proxy_url,
        "https": proxy_url
    }
    print(f"🔒 已啟用HTTP代理: {HTTP_PROXY_HOST}:{HTTP_PROXY_PORT}")
    
    # 設定環境變數，讓子進程也能使用代理
    os.environ["HTTP_PROXY"] = proxy_url
    os.environ["HTTPS_PROXY"] = proxy_url
else:
    print("ℹ️ 未啟用HTTP代理")

# --- 1. 傳送 Telegram 訊息函數 ---
def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    response = requests.post(url, json=payload, proxies=proxies)
    success = response.status_code == 200
    if success:
        print("✅ Telegram 訊息發送成功！")
    else:
        print(f"❌ Telegram 訊息發送失敗，狀態碼：{response.status_code}")
    return success

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
    fifteen_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=15)
    since = fifteen_minutes_ago.isoformat()

    print(f"🔍 抓取從 {since} 之後的貼文...")

    try:
        cmd = ["truthbrush", "statuses", TRUTHSOCIAL_SEARCH_USERNAME, "--no-replies", "--created-after", since]
        print("執行命令:", " ".join(cmd))
        
        # 設定環境變數，讓 truthbrush 使用代理
        env = os.environ.copy()
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env
        )
        
        # 檢查命令是否執行成功
        if result.returncode != 0:
            print(f"❌ truthbrush 命令執行失敗，錯誤碼: {result.returncode}")
            print(f"錯誤輸出: {result.stderr}")
            
            # 檢查是否為認證錯誤
            if "Failed login request" in result.stderr or "HTTP Error 403" in result.stderr:
                print("⚠️ 認證錯誤: truthbrush 無法登入 Truth Social 平台")
                print("請檢查以下可能的問題:")
                print("1. truthbrush 的認證資訊是否正確")
                print("2. 伺服器的 IP 是否被 Truth Social 封鎖")
                print("3. Truth Social API 是否有變更或限制")
                print("4. 代理設定是否正確")
            
            return []
            
        # 檢查輸出是否為空
        if not result.stdout.strip():
            print("⚠️ truthbrush 命令執行成功，但沒有返回任何資料")
            return []
            
        print(f"✅ truthbrush 命令執行成功，開始解析資料...")
        
        try:
            posts = [json.loads(line) for line in result.stdout.strip().splitlines() if line.strip()]
            print(f"📊 解析到 {len(posts)} 則貼文")
        except json.JSONDecodeError as je:
            print(f"❌ JSON 解析錯誤: {je}")
            print(f"原始輸出: {result.stdout[:200]}..." if len(result.stdout) > 200 else result.stdout)
            return []

        # 過濾掉轉發的貼文
        original_posts = []
        for post in posts:
            # 獲取貼文內容並清除 HTML 標籤
            from html import unescape
            import re
            content_html = post.get("content", "")
            content_text = re.sub(r"<[^>]*>", "", content_html).strip()
            
            # 檢查是否為轉發貼文且有文字內容
            if (post.get("reblog") is None and 
                not content_html.startswith("RT @") and 
                content_text):  # 確保有文字內容
                original_posts.append(post)
            else:
                reason = "轉發貼文" if post.get("reblog") is not None or content_html.startswith("RT @") else "無文字內容"
                print(f"🔄 過濾掉一則貼文: ID {post.get('id')} (原因: {reason})")
                
        return original_posts
    except FileNotFoundError as fnf:
        print(f"❌ 找不到 truthbrush 命令: {fnf}")
        print("請確認 truthbrush 已正確安裝在伺服器上，並且在 PATH 環境變數中")
        return []
    except Exception as e:
        print(f"❌ 抓取貼文時發生錯誤: {type(e).__name__}: {e}")
        import traceback
        print(f"詳細錯誤訊息: {traceback.format_exc()}")
        return []

# --- 5. 將 HTML 貼文轉成純文字 ---
def extract_post_text(post):
    # 處理 HTML content
    from html import unescape
    import re
    content_html = post.get("content", "")
    content_text = re.sub(r"<[^>]*>", "", content_html)
    return unescape(content_text.strip())

# --- 6. 使用 OpenRouter AI 分析貼文是否影響虛擬貨幣、股市 ---
def analyze_post_impact(text):
    try:
        print("🤖 使用 OpenRouter AI 分析貼文影響...")
        url = "https://openrouter.ai/api/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "openai/gpt-oss-20b:free",
            "messages": [
                {
                    "role": "user",
                    "content": f"{text} 分析以上這則大括號內的貼文，是否會影響虛擬貨幣、股市，如果會影響的話，回答規則如下：[Yes!Yes!Yes!]{{將大括號的貼文翻譯成繁體中文}}，如果不會影響的話，只需要回答：[No!No!No!]"
                }
            ]
        }
        
        response = requests.post(url, headers=headers, json=payload, proxies=proxies)
        
        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']
            print(f"✅ OpenRouter AI 分析結果: {content[:100]}...")
            return content
        else:
            print(f"❌ OpenRouter AI 請求失敗，狀態碼：{response.status_code}")
            print(f"錯誤訊息：{response.text}")
            return None
            
    except Exception as e:
        print(f"❌ OpenRouter AI 分析失敗: {e}")
        return None
    
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
            print(f"📢 分析 {len(new_posts)} 篇新貼文")

            # 按發文時間排序，舊的先通知
            for post in sorted(new_posts, key=lambda x: x["created_at"]):
                display_name = post["account"]["display_name"]
                text = extract_post_text(post)
                url = post["url"]
                media = post.get("media_attachments", [])
                media_note = "\n🎥 <i>含有影片</i>" if any(m['type'] == 'video' for m in media) else ""
                
                # 使用 OpenRouter AI 分析貼文影響
                analysis_result = analyze_post_impact(text)
                
                if analysis_result:
                    if analysis_result.startswith("[Yes!Yes!Yes!]"):
                        # 擷取大括號內的翻譯內容
                        import re
                        translation_match = re.search(r'\{([^}]+)\}', analysis_result)
                        if translation_match:
                            translated_content = translation_match.group(1)
                            msg = f"<b>{display_name} 發文：</b>\n{text}\n\n<b>分析結果：</b>\n{translated_content}\n🔗 {url}{media_note}"
                            send_telegram_message(msg)
                            print("📤 貼文影響市場，已發送 Telegram 訊息")
                        else:
                            print("⚠️ AI 回應格式異常，無法擷取翻譯內容")
                    elif analysis_result.startswith("[No!No!No!]"):
                        print("📝 貼文不影響市場，不發送訊息")
                    else:
                        print(f"⚠️ AI 回應格式未知: {analysis_result[:50]}...")
                else:
                    print("❌ AI 分析失敗，跳過此貼文")

            # 更新已通知清單
            save_seen_ids(seen_ids)
        else:
            print("🕒 無新貼文")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()