import requests
import json
import os
import time
from datetime import datetime
from bs4 import BeautifulSoup

TELEGRAM_BOT_TOKEN = "8728034905:AAG8AfIziMpCst9jUo1iQJM0FV6YUrQjSSk"
TELEGRAM_CHAT_ID   = "1656687130"

SEEN_FILE = "seen_tenders.json"
SHEETS_FILE = "tenders.csv"

# Категории с их basecode ID из HTML сайта
SEARCH_PARAMS = [
    {"app_basecode": "18999", "label": "45100000 - Подготовка стройплощадки"},
    {"app_basecode": "18951", "label": "37400000 - Спортивные товары"},
    {"app_basecode": "18965", "label": "37500000 - Игры и аттракционы"},
    {"app_codes": "37420000",  "label": "CPV 37420000 - Гимнастика"},
    {"app_codes": "37440000",  "label": "CPV 37440000 - Фитнес"},
    {"app_codes": "45112700",  "label": "CPV 45112700 - Ландшафт"},
    {"app_codes": "45112720",  "label": "CPV 45112720 - Ландшафт спортплощадок"},
]

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
        print(f"  Telegram: {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        print(f"  Telegram ошибка: {e}")
        return False

def search_tenders(params):
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,ka;q=0.8",
        "Referer": "https://tenders.procurement.gov.ge/public/?lang=ru",
        "Origin": "https://tenders.procurement.gov.ge",
        "Content-Type": "application/x-www-form-urlencoded",
    })

    # Сначала загружаем главную страницу для куков
    try:
        session.get("https://tenders.procurement.gov.ge/public/?lang=ru", timeout=15)
        time.sleep(1)
    except:
        pass

    data = {
        "action": "search_app",
        "app_t": "0",
        "search": "1",
        "app_reg_id": "",
        "app_shems_id": "0",
        "org_a": "",
        "app_monac_id": "0",
        "org_b": "",
        "app_particip_status_id": "0",
        "app_donor_id": "0",
        "app_status": "10",
        "app_agr_status": "0",
        "app_type": "0",
        "app_basecode": params.get("app_basecode", "0"),
        "app_codes": params.get("app_codes", ""),
        "app_date_type": "1",
        "app_date_from": "",
        "app_date_tlll": "",
        "app_amount_from": "",
        "app_amount_to": "",
        "app_currency": "2",
        "app_pricelist": "0",
    }

    try:
        r = session.post(
            "https://tenders.procurement.gov.ge/public/library/controller.php",
            data=data,
            timeout=30
        )
        print(f"  HTTP {r.status_code}, размер: {len(r.text)} байт")
        if r.status_code == 200 and len(r.text) > 100:
            return parse_html(r.text)
        else:
            print(f"  Ответ: {r.text[:200]}")
    except Exception as e:
        print(f"  Ошибка: {e}")
    return []

def parse_html(html):
    soup = BeautifulSoup(html, "html.parser")
    tenders = []

    print(f"  HTML превью: {html[:300]}")

    # Ищем таблицу с результатами
    tables = soup.find_all("table")
    print(f"  Таблиц найдено: {len(tables)}")

    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 3:
                continue

            links = row.find_all("a")
            if not links:
                continue

            for link in links:
                onclick = link.get("onclick", "")
                href = link.get("href", "")

                import re
                tender_id = None
                if "ShowApp" in onclick:
                    m = re.search(r"ShowApp\((\d+)", onclick)
                    if m:
                        tender_id = m.group(1)
                elif "go=" in href:
                    m = re.search(r"go=(\d+)", href)
                    if m:
                        tender_id = m.group(1)

                if tender_id:
                    col_texts = [c.get_text(strip=True) for c in cols]
                    tender = {
                        "id": tender_id,
                        "reg_id": col_texts[0] if len(col_texts) > 0 else "",
                        "name": link.get_text(strip=True),
                        "org": col_texts[2] if len(col_texts) > 2 else "",
                        "date": col_texts[3] if len(col_texts) > 3 else "",
                        "price": col_texts[4] if len(col_texts) > 4 else "",
                        "deadline": col_texts[5] if len(col_texts) > 5 else "",
                        "status": col_texts[6] if len(col_texts) > 6 else "",
                    }
                    tenders.append(tender)
                    break

    print(f"  Тендеров распарсено: {len(tenders)}")
    return tenders

def save_to_csv(tender, label):
    exists = os.path.exists(SHEETS_FILE)
    with open(SHEETS_FILE, "a", encoding="utf-8-sig", newline="") as f:
        if not exists:
            f.write("Дата,ID,Номер,Название,Организация,Цена,Дедлайн,Категория,Ссылка\n")
        f.write(",".join([
            datetime.now().strftime("%d.%m.%Y"),
            tender.get("id",""),
            tender.get("reg_id",""),
            f'"{tender.get("name","")}"',
            f'"{tender.get("org","")}"',
            tender.get("price",""),
            tender.get("deadline",""),
            f'"{label}"',
            f'https://tenders.procurement.gov.ge/public/?lang=ru#go={tender.get("id","")}'
        ]) + "\n")

def format_msg(tender, label):
    tid = tender.get("id","")
    return (
        f"🏋️ <b>НОВЫЙ ТЕНДЕР</b>\n"
        f"{'─'*28}\n"
        f"📋 <b>{tender.get('reg_id','N/A')}</b>\n"
        f"📌 {tender.get('name','Без названия')}\n"
        f"🏢 {tender.get('org','—')}\n"
        f"💰 {tender.get('price','—')}\n"
        f"📅 {tender.get('deadline','—')}\n"
        f"🏷 {label}\n"
        f"🔗 <a href='https://tenders.procurement.gov.ge/public/?lang=ru#go={tid}'>Открыть</a>"
    )

def check_tenders():
    print(f"\n{'='*50}")
    print(f"[{datetime.now().strftime('%d.%m.%Y %H:%M')}] Проверяю тендеры...")

    seen = load_seen()
    new_count = 0

    for params in SEARCH_PARAMS:
        label = params["label"]
        print(f"\n  🔍 {label}...")
        tenders = search_tenders(params)

        for t in tenders:
            uid = t.get("id") or t.get("reg_id","")
            if uid and uid not in seen:
                seen.add(uid)
                save_to_csv(t, label)
                send_telegram(format_msg(t, label))
                new_count += 1
                time.sleep(0.5)
        time.sleep(3)

    save_seen(seen)
    send_telegram(f"📊 Проверка {datetime.now().strftime('%d.%m.%Y %H:%M')}\nНовых тендеров: <b>{new_count}</b>")
    print(f"\n✅ Готово! Новых тендеров: {new_count}")

if __name__ == "__main__":
    if not os.path.exists(SEEN_FILE):
        send_telegram("🤖 <b>Бот запущен!</b>\n✅ Мониторинг тендеров Грузии активен")
    check_tenders()
