# 🇺🇸 Trump Notifier 🗞️📢

自動追蹤 Donald Trump 在 [Truth Social](https://truthsocial.com/) 上的新貼文，每 10 分鐘掃描一次，使用 AI 智能分析貼文是否影響虛擬貨幣、股市，並透過 Telegram Bot 推播重要通知。

## ✨ 功能特色

- ⏱️ 每 10 分鐘自動檢查 Trump 新貼文
- 🤖 使用 OpenRouter AI 智能分析貼文市場影響力
- 📊 只推送可能影響虛擬貨幣、股市的重要貼文
- 🌐 AI 自動翻譯貼文為繁體中文
- 📤 自動發送重要貼文到指定的 Telegram 頻道或聊天室
- 🔁 不會重複推送相同貼文
- 📹 偵測影片貼文並加上提示
- 🧪 透過 [truthbrush](https://github.com/stanfordio/truthbrush) 擷取 Trump 最新貼文

---

## 📦 安裝步驟

### 1. Clone 專案

```bash
git clone https://github.com/taiwanJK/trump-notifier.git
cd trump-notifier
```

### 2. 建立虛擬環境並安裝依賴
```bash
python -m venv truthbrush-env
source truthbrush-env/bin/activate
pip install -r requirements.txt
```

### 3. 安裝 truthbrush CLI 工具
```bash
pip install git+https://github.com/stanfordio/truthbrush.git
``` 
> 若在 Linux 環境出現 externally-managed-environment 錯誤，請務必使用虛擬環境執行安裝。


---

## 🔐 建立環境變數 .env
請參考 .env.template 檔案建立 .env：
```bash
TRUTHSOCIAL_SEARCH_USERNAME=realDonaldTrump         # 要追蹤的使用者
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here     # Telegram Bot Token
TELEGRAM_CHAT_ID=-100xxxxxxxxxx                     # 頻道/群組 ID（注意：頻道需設為公開）
OPENROUTER_API_KEY=your_openrouter_api_key_here     # OpenRouter AI API Key
HTTP_PROXY_ENABLED=false                            # 是否啟用代理 (true/false)
HTTP_PROXY_HOST=your_proxy_host                     # 代理伺服器主機名稱或 IP
HTTP_PROXY_PORT=your_proxy_port                     # 代理伺服器連接埠
HTTP_PROXY_USERNAME=your_proxy_username             # 代理伺服器使用者名稱（如需驗證）
HTTP_PROXY_PASSWORD=your_proxy_password             # 代理伺服器密碼（如需驗證）
```

建立指令：
```bash
cp .env.template .env
```

### 🤖 OpenRouter AI 設定說明

本系統使用 OpenRouter AI 來智能分析貼文內容：

1. 前往 [OpenRouter](https://openrouter.ai/) 註冊帳號
2. 取得 API Key
3. 將 API Key 填入 `.env` 檔案的 `OPENROUTER_API_KEY`
4. 系統使用 `openai/gpt-oss-20b:free` 模型進行分析

**AI 分析邏輯：**
- 🟢 **有影響市場**：AI 回應 `[Yes!Yes!Yes!]{中文翻譯}` → 發送 Telegram 訊息
- 🔴 **無影響市場**：AI 回應 `[No!No!No!]` → 不發送訊息

### 代理設定說明

若您在網路受限的環境中運行（例如某些國家/地區可能無法直接訪問 Truth Social），可以通過設定 HTTP 代理來解決：

1. 將 HTTP_PROXY_ENABLED 設為 true
2. 填入您的代理伺服器資訊（主機、連接埠）
3. 如果代理需要驗證，請填入使用者名稱和密碼
系統會自動將代理設定應用於所有網路請求，包括 truthbrush 工具和 Telegram API 呼叫。

---

## 🚀 執行主程式
```bash
python trump_notifier.py
```
每 10 分鐘將自動檢查 Trump 是否有新發文，使用 AI 智能分析是否影響虛擬貨幣、股市，只推送重要的市場相關貼文到 Telegram。

### 🧪 測試 OpenRouter AI 整合
```bash
python tmp_rovodev_test_openrouter.py
```
執行測試腳本確認 OpenRouter AI API 連接正常。
