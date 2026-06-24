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
CURRENT_NEWS_API_KEY = os.environ.get("CURRENT_NEWS_API_KEY")

# Cloudflare 瀏覽器指紋模擬 — 若未來被封鎖只需改這一行
# 可用值參考 curl_cffi BrowserType: firefox133, firefox135, chrome136, chrome124 等
IMPERSONATE = "firefox133"

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
    
    # 設定環境變數，truthbrush 在 import 時讀取（需在 import 前設定）
    os.environ["HTTP_PROXY"] = proxy_url
    os.environ["HTTPS_PROXY"] = proxy_url
    os.environ["http_proxy"] = proxy_url
    os.environ["https_proxy"] = proxy_url
else:
    print("ℹ️ 未啟用HTTP代理")

# Monkey-patch truthbrush 使用可設定的 impersonate，避免 Cloudflare 封鎖
import truthbrush.api as _tb_api
import curl_cffi as _curl_cffi

def _patched_get(self, url, params=None):
    from loguru import logger
    try:
        resp = self._make_session().get(
            _tb_api.API_BASE_URL + url,
            params=params,
            proxies=_tb_api.proxies,
            impersonate=IMPERSONATE,
            headers={
                "Authorization": "Bearer " + self.auth_id,
                "User-Agent": _tb_api.USER_AGENT,
            },
        )
    except _curl_cffi.curl.CurlError as e:
        logger.error(f"Curl error: {e}")
        return None
    self._check_ratelimit(resp)
    try:
        r = resp.json()
    except json.JSONDecodeError:
        logger.error(f"Failed to decode JSON: {resp.text}")
        r = None
    return r

_tb_api.Api._get = _patched_get

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
    import re

    fifteen_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=15)
    print(f"🔍 抓取從 {fifteen_minutes_ago.isoformat()} 之後的貼文（impersonate={IMPERSONATE}）...")

    try:
        api = _tb_api.Api()
        posts = list(api.pull_statuses(
            TRUTHSOCIAL_SEARCH_USERNAME,
            replies=False,
            created_after=fifteen_minutes_ago,
        ))
        print(f"📊 抓取到 {len(posts)} 則貼文")

        original_posts = []
        for post in posts:
            content_html = post.get("content", "")
            content_text = re.sub(r"<[^>]*>", "", content_html).strip()
            if (post.get("reblog") is None and
                    not content_html.startswith("RT @") and
                    content_text):
                original_posts.append(post)
            else:
                reason = "轉發貼文" if post.get("reblog") is not None or content_html.startswith("RT @") else "無文字內容"
                print(f"🔄 過濾掉一則貼文: ID {post.get('id')} (原因: {reason})")

        return original_posts

    except TypeError as e:
        print(f"❌ 無法查詢用戶（可能是 Cloudflare 封鎖）: {e}")
        print(f"💡 嘗試修改 IMPERSONATE 變數，目前為 '{IMPERSONATE}'")
        return []
    except Exception as e:
        import traceback
        print(f"❌ 抓取貼文時發生錯誤: {type(e).__name__}: {e}")
        print(f"詳細錯誤訊息: {traceback.format_exc()}")
        return []

# --- 5a. 從 Currents API 抓取最新新聞 ---
def fetch_currents_news():
    """從 Currents API 取得最新英文新聞，回傳新聞列表（最多 20 則）"""
    if not CURRENT_NEWS_API_KEY:
        print("⚠️ 未設定 CURRENT_NEWS_API_KEY，跳過新聞比對")
        return []

    try:
        url = "https://api.currentsapi.services/v1/latest-news"
        params = {
            "apiKey": CURRENT_NEWS_API_KEY,
            "language": "en",
        }
        response = requests.get(url, params=params, proxies=proxies, timeout=10)

        if response.status_code == 200:
            data = response.json()
            news_list = data.get("news", [])
            print(f"📰 Currents API 取得 {len(news_list)} 則新聞")
            return news_list
        else:
            print(f"❌ Currents API 請求失敗，狀態碼：{response.status_code}，訊息：{response.text[:200]}")
            return []
    except Exception as e:
        print(f"❌ 抓取 Currents 新聞時發生錯誤: {e}")
        return []


# --- 5b. 比對貼文關鍵字與新聞，找出相關新聞 ---
def find_matching_news(post_text, news_list):
    """
    從貼文中提取有意義的關鍵字，與新聞標題/描述比對，
    回傳相關新聞列表（最多 5 則）。
    """
    import re

    # 英文停用詞（過濾無意義的詞）
    STOP_WORDS = {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "that", "this", "these", "those",
        "it", "its", "he", "she", "we", "they", "i", "you", "my", "our",
        "their", "his", "her", "not", "no", "so", "as", "if", "into", "about",
        "up", "out", "over", "then", "than", "more", "also", "just", "get",
        "all", "can", "what", "very", "new", "now", "said", "says", "say",
    }

    # 提取貼文關鍵字（長度 >= 4 的非停用詞）
    words = re.findall(r"[a-zA-Z]{4,}", post_text.lower())
    keywords = {w for w in words if w not in STOP_WORDS}

    if not keywords:
        return []

    matched = []
    for article in news_list:
        title = (article.get("title") or "").lower()
        description = (article.get("description") or "").lower()
        combined = f"{title} {description}"

        # 計算命中的關鍵字數
        hits = sum(1 for kw in keywords if kw in combined)
        if hits >= 2:  # 至少 2 個關鍵字命中
            matched.append((hits, article))

    # 按命中數排序，取前 5 則
    matched.sort(key=lambda x: x[0], reverse=True)
    result = [article for _, article in matched[:5]]

    if result:
        print(f"🔗 找到 {len(result)} 則與貼文相關的新聞")
    else:
        print("🔍 未找到與貼文關鍵字相符的新聞")

    return result


# --- 5. 將 HTML 貼文轉成純文字 ---
def extract_post_text(post):
    # 處理 HTML content
    from html import unescape
    import re
    content_html = post.get("content", "")
    content_text = re.sub(r"<[^>]*>", "", content_html)
    return unescape(content_text.strip())

# --- 6. 使用 OpenRouter AI 分析貼文是否影響虛擬貨幣、股市 ---
def analyze_post_impact(text, related_news=None):
    try:
        import re
        print("🤖 使用 OpenRouter AI 分析貼文影響...")
        url = "https://openrouter.ai/api/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }

        system_prompt = (
            "You are a financial news analyst. Analyze the given post and output ONLY valid JSON (no markdown, no explanation).\n"
            "Output format:\n"
            "{\n"
            '  "summary": "<1-2 sentence summary in Traditional Chinese of the core event>",\n'
            '  "impact_score": <integer 0-100, how much this affects financial markets>,\n'
            '  "event_category": "<one of: tariff_trade | geopolitical_war | geopolitical_energy_shock | fed_rates | usd_policy | crypto_policy | domestic_politics | non_market_noise>",\n'
            '  "impact": [\n'
            '    { "asset": "BTC", "score": <integer -3 to 3>, "score_1d": <integer -3 to 3, optional, only if short and mid-term differ> },\n'
            '    { "asset": "QQQ", "score": <integer -3 to 3> },\n'
            '    { "asset": "DXY", "score": <integer -3 to 3> },\n'
            '    { "asset": "GOLD", "score": <integer -3 to 3> },\n'
            '    { "asset": "OIL", "score": <integer -3 to 3> }\n'
            "  ]\n"
            "}\n"
            "Score scale: +3=strong bullish, +2=bullish, +1=weak bullish, 0=neutral, -1=weak bearish, -2=bearish, -3=strong bearish.\n"
            "\n"
            "Asset-specific judgment rules:\n"
            "OIL: bullish if Middle East conflict, tanker route disruption, sanctions, supply disruption risk; bearish if production increase, peace talks, supply recovery.\n"
            "GOLD: bullish if risk-off sentiment, war risk, inflation risk; bearish if risk decreases, USD real rates surge.\n"
            "DXY: bullish if short-term risk-off, capital flows back to USD; bearish if post weakens US credibility, raises rate-cut expectations, or undermines USD dominance. Use 0 if signals conflict.\n"
            "QQQ: bullish if risk-on, rate-cut expectations, tech/AI tailwinds; bearish if oil prices rise, inflation, higher yields, or geopolitical risk increases.\n"
            "BTC: bullish if risk-on, crypto policy tailwind, USD weakening; bearish (short-term/15m) if sudden war, leveraged deleveraging, or stock market crash; if event drives inflation-hedge or de-dollarization narrative, 1d may turn bullish. "
            "If short-term (score) and mid-term (score_1d) differ, output both fields.\n"
            "\n"
            "Other rules:\n"
            "- impact_score 85-100: major market-moving event (policy, war, crisis)\n"
            "- impact_score 60-84: moderate impact (trade, regulation, economy)\n"
            "- impact_score 40-59: minor impact\n"
            "- impact_score 0-39: no meaningful market impact\n"
            "- event_category must be exactly one of the listed values.\n"
            "- Output ONLY the JSON object, nothing else."
        )

        # 組合用戶訊息：貼文 + 相關新聞（若有）
        user_content = f"Post:\n{text}"
        if related_news:
            news_context_lines = []
            for i, article in enumerate(related_news, 1):
                title = article.get("title", "")
                description = article.get("description", "") or ""
                published = article.get("published", "")
                source_url = article.get("url", "")
                news_context_lines.append(
                    f"[News {i}] {title}\n"
                    f"  Published: {published}\n"
                    f"  Summary: {description[:200]}\n"
                    f"  URL: {source_url}"
                )
            news_context = "\n\n".join(news_context_lines)
            user_content += (
                f"\n\n---\nRelated News (use to assess credibility and context):\n{news_context}"
            )
            print(f"📎 附加 {len(related_news)} 則相關新聞至分析請求")

        payload = {
            "model": "openai/gpt-oss-120b:free",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ]
        }

        response = requests.post(url, headers=headers, json=payload, proxies=proxies)

        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content'].strip()
            print(f"✅ OpenRouter AI 原始回應: {content[:200]}...")

            # 擷取 JSON（防止 LLM 包了 markdown code block）
            json_match = re.search(r'\{[\s\S]*\}', content)
            if not json_match:
                print("❌ 無法從回應中擷取 JSON")
                return None

            parsed = json.loads(json_match.group(0))
            return parsed
        else:
            print(f"❌ OpenRouter AI 請求失敗，狀態碼：{response.status_code}")
            print(f"錯誤訊息：{response.text}")
            return None

    except json.JSONDecodeError as e:
        print(f"❌ OpenRouter AI 回應 JSON 解析失敗: {e}")
        return None
    except Exception as e:
        print(f"❌ OpenRouter AI 分析失敗: {e}")
        return None


# --- 6b. 將分析結果格式化為 Telegram 訊息 ---
def format_analysis_message(display_name, text, url, media_note, analysis, related_news=None):
    impact_score = analysis.get("impact_score", 0)
    summary = analysis.get("summary", "")
    event_category = analysis.get("event_category", "")
    impacts = analysis.get("impact", [])

    # 決定影響等級
    if impact_score >= 85:
        level_label = "🚨 <b>HIGH</b>"
    elif impact_score >= 60:
        level_label = "🟨 <b>MEDIUM</b>"
    elif impact_score >= 40:
        level_label = "🟦 <b>LOW</b>"
    else:
        level_label = "⚪ <b>IGNORE</b>"

    # 市場事件分類對應
    category_map = {
        "tariff_trade":             "🛃 關稅／貿易",
        "geopolitical_war":         "⚔️ 地緣政治／戰爭",
        "geopolitical_energy_shock":"⚡ 地緣政治／能源衝擊",
        "fed_rates":                "🏦 聯準會／利率",
        "usd_policy":               "💵 美元政策",
        "crypto_policy":            "🪙 加密貨幣政策",
        "domestic_politics":        "🏛️ 國內政治",
        "non_market_noise":         "📢 非市場雜訊",
    }
    category_label = category_map.get(event_category, f"❓ {event_category}")

    # 格式化市場影響
    score_map = {
        3:  "強利多 ↑↑↑",
        2:  "利多 ↑↑",
        1:  "弱利多 ↑",
        0:  "中性 →",
        -1: "弱利空 ↓",
        -2: "利空 ↓↓",
        -3: "強利空 ↓↓↓",
    }

    def score_label(s):
        s = max(-3, min(3, int(s)))  # 防禦性 clamp
        return score_map.get(s, "中性 →")

    market_lines = []
    for item in impacts:
        asset = item.get("asset", "")
        score = item.get("score", 0)
        line = f"  - {asset}: {score_label(score)}"
        # BTC 短中線不同時，附加 1d 標註
        if asset == "BTC" and "score_1d" in item:
            line += f"（短線） / {score_label(item['score_1d'])}（1d）"
        market_lines.append(line)

    market_section = "\n".join(market_lines) if market_lines else "  （無明顯影響）"

    # 相關新聞來源區段
    news_section = ""
    if related_news:
        news_lines = []
        for i, article in enumerate(related_news[:3], 1):  # 最多顯示 3 則
            title = article.get("title", "")
            article_url = article.get("url", "")
            news_lines.append(f"  {i}. <a href=\"{article_url}\">{title}</a>")
        news_section = "\n\n<b>📰 相關新聞（可信度來源）：</b>\n" + "\n".join(news_lines)

    msg = (
        f"<b>{display_name} 發文：</b>\n"
        f"{text}\n\n"
        f"<b>摘要：</b>\n{summary}\n\n"
        f"<b>影響等級：</b> {level_label}（{impact_score}/100）\n"
        f"<b>市場事件：</b> {category_label}\n\n"
        f"<b>市場影響：</b>\n{market_section}"
        f"{news_section}\n\n"
        f"🔗 {url}{media_note}"
    )
    return msg
    
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

            # 抓取 Currents 最新新聞（每輪只抓一次，供所有新貼文共用）
            currents_news = fetch_currents_news()

            # 按發文時間排序，舊的先通知
            for post in sorted(new_posts, key=lambda x: x["created_at"]):
                display_name = post["account"]["display_name"]
                text = extract_post_text(post)
                url = post["url"]
                media = post.get("media_attachments", [])
                media_note = "\n🎥 <i>含有影片</i>" if any(m['type'] == 'video' for m in media) else ""

                # 比對貼文與新聞關鍵字，找出相關新聞
                related_news = find_matching_news(text, currents_news)

                # 使用 OpenRouter AI 分析貼文影響（附帶相關新聞）
                analysis_result = analyze_post_impact(text, related_news=related_news)

                if analysis_result:
                    impact_score = analysis_result.get("impact_score", 0)
                    print(f"📊 影響分數: {impact_score}/100")

                    if impact_score >= 40:
                        msg = format_analysis_message(display_name, text, url, media_note, analysis_result, related_news=related_news)
                        send_telegram_message(msg)
                        print("📤 貼文影響市場，已發送 Telegram 訊息")
                    else:
                        print(f"📝 影響分數過低（{impact_score}），不發送訊息")
                else:
                    print("❌ AI 分析失敗，跳過此貼文")

            # 更新已通知清單
            save_seen_ids(seen_ids)
        else:
            print("🕒 無新貼文")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()