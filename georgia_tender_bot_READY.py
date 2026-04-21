"""
Georgia Tender Monitor
Скрапер tenders.procurement.gov.ge
Отправляет в Google Sheets + Telegram уведомление
"""

import requests
import json
import os
import time
from datetime import datetime
from bs4 import BeautifulSoup

TELEGRAM_BOT_TOKEN = "8728034905:AAG8AfIziMpCst9jUo1iQJM0FV6YUrQjSSk"
TELEGRAM_CHAT_ID   = "1656687130"

BASE_URL = "https://tenders.procurement.gov.ge/public/library/controller.php"

# Категории закупки (basecode из HTML)
CATEGORIES = {
    "18999": "45100000 - Подготовка строительной площадки",
    "18951": "37400000 - Спортивные товары и оборудование",
    "18965": "37500000 - Игры и аттракционы",
}

# CPV коды для поля app_codes
CPV_CODES = [
    "37420000",
    "37440000",
    "45112700",
    "45100000",
    "45112720",
]

SEEN_FILE = "seen_tenders.json"
SHEETS_FILE = "tenders.csv"

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False)

def send_telegram(msg):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=15
        )
        return r.status_code == 200
    except:
        return False

def search_tenders(basecode=None, cpv_code=None):
    """Поиск через POST форму сайта"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://tenders.procurement.gov.ge/public/?lang=ru",
        "Content-Type": "application/x-www-form-urlencoded",
    })

    data = {
        "action": "search_app",
        "app_t": "0",
        "search": "1",
        "app_reg_id": "",
        "app_shems_id": "0",
        "app_monac_id": "0",
        "app_donor_id": "0",
        "app_status": "10",  # Только "Объявлен"
        "app_agr_status": "0",
        "app_type": "0",
        "app_basecode": basecode or "0",
        "app_codes": cpv_code or "",
        "app_date_type": "1",
        "app_date_from": "",
        "app_date_tlll": "",
        "app_amount_from": "",
        "app_amount_to": "",
        "app_currency": "2",
        "app_pricelist": "0",
    }

    try:
        r = session.post(BASE_URL, data=data, timeout=30)
        if r.status_code == 200:
            return parse_results(r.text)
    except Exception as e:
        print(f"  Ошибка запроса: {e}")
    return []

def parse_results(html):
    """Парсим HTML ответ и извлекаем тендеры"""
    soup = BeautifulSoup(html, "html.parser")
    tenders = []

    # Ищем строки таблицы с тендерами
    rows = soup.find_all("tr")
    for row in rows:
        cols = row.find_all("td")
        if len(cols) >= 4:
            # Ищем ссылку на тендер
            link_tag = row.find("a")
            if not link_tag:
                continue

            href = link_tag.get("href", "")
            if "go=" not in href and "ShowApp" not in str(row):
                continue

            tender = {}

            # ID тендера из onclick или href
            onclick = link_tag.get("onclick", "")
            if "ShowApp" in onclick:
                import re
                match = re.search(r"ShowApp\((\d+)", onclick)
                if match:
                    tender["id"] = match.group(1)

            tender["name"] = link_tag.get_text(strip=True)

            # Остальные колонки
            col_texts = [c.get_text(strip=True) for c in cols]
            if len(col_texts) > 1:
                tender["reg_id"] = col_texts[0] if col_texts else ""
            if len(col_texts) > 2:
                tender["org"] = col_texts[1]
            if len(col_texts) > 3:
                tender["status"] = col_texts[2]
            if len(col_texts) > 4:
                tender["date"] = col_texts[3]
            if len(col_texts) > 5:
                tender["price"] = col_texts[4]
            if len(col_texts) > 6:
                tender["deadline"] = col_texts[5]

            if tender.get("id") or tender.get("name"):
                tenders.append(tender)

    return tenders

def get_tender_url(tender_id):
    return f"https://tenders.procurement.gov.ge/public/?lang=ru#go={tender_id}"

def save_to_csv(tender, category):
    """Сохраняем тендер в CSV файл"""
    file_exists = os.path.exists(SHEETS_FILE)
    with open(SHEETS_FILE, "a", encoding="utf-8-sig", newline="") as f:
        if not file_exists:
            f.write("Дата добавления,ID,Номер,Название,Организация,Цена,Дедлайн,Категория,Ссылка\n")
        row = ",".join([
            datetime.now().strftime("%d.%m.%Y"),
            str(tender.get("id", "")),
            str(tender.get("reg_id", "")),
            f'"{tender.get("name", "")}"',
            f'"{tender.get("org", "")}"',
            str(tender.get("price", "")),
            str(tender.get("deadline", "")),
            f'"{category}"',
            get_tender_url(tender.get("id", ""))
        ])
        f.write(row + "\n")

def format_telegram_msg(tender, category):
    tid = tender.get("id", "")
    return (
        f"🏋️ <b>НОВЫЙ ТЕНДЕР</b>\n"
        f"{'─'*28}\n"
        f"📋 <b>{tender.get('reg_id', 'N/A')}</b>\n"
        f"📌 {tender.get('name', 'Без названия')}\n"
        f"🏢 {tender.get('org', 'Не указано')}\n"
        f"💰 {tender.get('price', '—')}\n"
        f"📅 Дедлайн: {tender.get('deadline', '—')}\n"
        f"🏷 {category}\n"
        f"🔗 <a href='{get_tender_url(tid)}'>Открыть тендер</a>"
    )

def check_tenders():
    print(f"\n{'='*50}")
    print(f"[{datetime.now().strftime('%d.%m.%Y %H:%M')}] Проверяю тендеры...")

    seen = load_seen()
    new_count = 0

    # 1. Поиск по категориям (basecode)
    for basecode, cat_name in CATEGORIES.items():
        print(f"\n  📂 {cat_name}...")
        tenders = search_tenders(basecode=basecode)
        for t in tenders:
            uid = t.get("id") or t.get("reg_id") or t.get("name", "")[:30]
            if uid and uid not in seen:
                seen.add(uid)
                save_to_csv(t, cat_name)
                send_telegram(format_telegram_msg(t, cat_name))
                new_count += 1
                print(f"    ✅ Новый: {t.get('reg_id')} — {t.get('name', '')[:50]}")
                time.sleep(0.5)
        time.sleep(2)

    # 2. Поиск по CPV кодам
    for cpv in CPV_CODES:
        print(f"\n  🔍 CPV {cpv}...")
        tenders = search_tenders(cpv_code=cpv)
        for t in tenders:
            uid = t.get("id") or t.get("reg_id") or t.get("name", "")[:30]
            if uid and uid not in seen:
                seen.add(uid)
                save_to_csv(t, f"CPV {cpv}")
                send_telegram(format_telegram_msg(t, f"CPV {cpv}"))
                new_count += 1
                print(f"    ✅ Новый: {t.get('reg_id')} — {t.get('name', '')[:50]}")
                time.sleep(0.5)
        time.sleep(2)

    save_seen(seen)

    summary = f"📊 Проверка {datetime.now().strftime('%d.%m.%Y %H:%M')}\nНайдено новых тендеров: <b>{new_count}</b>"
    send_telegram(summary)
    print(f"\n✅ Готово! Новых тендеров: {new_count}")
    print(f"📄 Сохранено в: {SHEETS_FILE}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        send_telegram("🤖 <b>Бот запущен!</b>\n✅ Мониторинг тендеров Грузии\n🏷 CPV: 37420000, 37440000, 45112700, 45112720")
        print("✅ Тест отправлен!")
    else:
        if not os.path.exists(SEEN_FILE):
            send_telegram("🤖 <b>Бот запущен!</b>\n✅ Мониторинг тендеров Грузии активен")
        check_tenders()
