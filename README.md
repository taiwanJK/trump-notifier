# 🇺🇸 Trump Notifier 🗞️📢

自動追蹤 Donald Trump 在 [Truth Social](https://truthsocial.com/) 上的新貼文，每 10 分鐘掃描一次，並透過 Telegram Bot 推播通知（附中文翻譯）。

## ✨ 功能特色

- ⏱️ 每 10 分鐘自動檢查 Trump 新貼文
- 📤 自動發送貼文內容到指定的 Telegram 頻道或聊天室
- 🌐 支援貼文英文翻譯成繁體中文（使用 `googletrans` + `LibreTranslate` fallback）
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
TRUTHSOCIAL_USERNAME=foo                            # 您的 Truth Social 使用者名稱
TRUTHSOCIAL_PASSWORD=bar                            # 您的 Truth Social 密碼               
TRUTHSOCIAL_SEARCH_USERNAME=realDonaldTrump         # 要追蹤的使用者
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here     # Telegram Bot Token
TELEGRAM_CHAT_ID=-100xxxxxxxxxx                     # 頻道/群組 ID（注意：頻道需設為公開）
```

建立指令：
```bash
cp .env.template .env
```

---

## 🚀 執行主程式
```bash
python trump_notifier.py
```
每 10 分鐘將自動檢查 Trump 是否有新發文，並即時發送 Telegram 通知。
