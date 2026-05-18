import requests
from bs4 import BeautifulSoup
import time
import json
import os
import logging
from datetime import datetime

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = "@briefingukraine"
CHECK_INTERVAL = 300
NEWS_URL = "https://www.ukr.net/news/main.html"
PUBLISHED_FILE = "published_news.json"
MAX_STORED_IDS = 500

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "uk-UA,uk;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def load_published():
    if os.path.exists(PUBLISHED_FILE):
        try:
            with open(PUBLISHED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("published", []))
        except Exception as e:
            log.warning(f"Не вдалося прочитати файл: {e}")
    return set()

def save_published(published):
    ids_list = list(published)
    if len(ids_list) > MAX_STORED_IDS:
        ids_list = ids_list[-MAX_STORED_IDS:]
    try:
        with open(PUBLISHED_FILE, "w", encoding="utf-8") as f:
            json.dump({"published": ids_list, "updated": datetime.now().isoformat()}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Не вдалося зберегти файл: {e}")

def fetch_news():
    try:
        response = requests.get(NEWS_URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
        response.encoding = "utf-8"
    except requests.RequestException as e:
        log.error(f"Помилка завантаження сторінки: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    news_items = []
    seen_urls = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href", "")
        text = a_tag.get_text(strip=True)

        if not text or len(text) < 15:
            continue
        if any(skip in href for skip in ["/tags/", "/source/", "javascript:", "#", "/news/"]):
            continue
        if "/cluster/" not in href and not href.startswith("http"):
            continue

        url = ("https://www.ukr.net" + href) if href.startswith("/") else href

        if url in seen_urls:
            continue
        seen_urls.add(url)

        time_text = ""
        parent = a_tag.parent
        for _ in range(4):
            if parent is None:
                break
            time_tag = parent.find(["span", "div", "time"], string=lambda s: s and ":" in s and len(s) <= 10)
            if time_tag:
                time_text = time_tag.get_text(strip=True)
                break
            parent = parent.parent

        news_items.append({"title": text, "url": url, "time": time_text})

    log.info(f"Знайдено {len(news_items)} новин")
    return news_items

def send_to_telegram(title, url, news_time):
        message = f"📰 {title}\n\n#Україна #новини"


    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHANNEL_ID, "text": message, "disable_web_page_preview": False}

    try:
        response = requests.post(api_url, json=payload, timeout=10)
        data = response.json()

        if data.get("ok"):
            log.info(f"Опубліковано: {title[:70]}")
            return True
        else:
            error_code = data.get("error_code")
            log.error(f"Telegram помилка {error_code}: {data.get('description', '')}")
            if error_code == 429:
                retry_after = data.get("parameters", {}).get("retry_after", 60)
                time.sleep(retry_after)
            return False
    except requests.RequestException as e:
        log.error(f"Помилка зєднання: {e}")
        return False

def main():
    print("UKR.NET Telegram Bot запущено!")
    print(f"Канал: {CHANNEL_ID}")
    print(f"Перевірка кожні: {CHECK_INTERVAL // 60} хвилин")

    if not BOT_TOKEN:
        log.error("BOT_TOKEN не знайдено! Додай його у Variables на Railway.")
        return

    published = load_published()
    log.info(f"Завантажено {len(published)} вже опублікованих новин")

    if len(published) == 0:
        log.info("Перший запуск - зберігаємо поточні новини без публікації...")
        news = fetch_news()
        for item in news:
            published.add(item["url"])
        save_published(published)
        log.info(f"Збережено {len(news)} новин. Нові публікуватимуться автоматично.")
        time.sleep(CHECK_INTERVAL)

    while True:
        log.info("Перевіряємо нові новини...")
        news = fetch_news()
        new_count = 0

        for item in news:
            if item["url"] not in published:
                if send_to_telegram(item["title"], item["url"], item["time"]):
                    published.add(item["url"])
                    new_count += 1
                    time.sleep(3)

        save_published(published)
        log.info(f"Опубліковано {new_count} нових новин" if new_count else "Нових новин немає")
        log.info(f"Наступна перевірка через {CHECK_INTERVAL // 60} хвилин...")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Бот зупинено")
