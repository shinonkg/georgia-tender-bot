import requests
import json
import os
import time
import re
from datetime import datetime
from bs4 import BeautifulSoup

TELEGRAM_BOT_TOKEN = "8728034905:AAG8AfIziMpCst9jUo1iQJM0FV6YUrQjSSk"
TELEGRAM_CHAT_ID   = "1656687130"

SEEN_FILE = "seen_tenders.json"
SHEETS_FILE = "tenders.csv"

SEARCH_PARAMS = [
    {"app_basecode": "18999", "app_codes": "", "label": "45100000 - Подготовка стройплощадки"},
    {"app_basecode": "18951", "app_codes": "", "label": "37400000 - Спортивные товары"},
    {"app_basecode": "18965", "app_codes": "", "label": "37500000 - Игры и аттракционы"},
    {"app_basecode": "0",     "app_codes": "37420000", "label": "CPV 37420000 - Гимнастика"},
    {"app_basecode": "0",     "app_codes": "37440000", "label": "CPV 37440000 - Фитнес"},
    {"app_basecode": "0",     "app_codes": "45112700", "label": "CPV 45112700 - Ландшафт"},
    {"app_basecode": "0",     "app_codes": "45112720", "label": "CPV 45112720 - Ландшафт спортплощадок"},
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
        if r.status_code == 200 and len(r.text) > 100:
            return parse_html(r.text)
    except Exception as e:
        print(f"  Ошибка: {e}")
    return []

def parse_html(html):
    soup = BeautifulSoup(html, "html.parser")
    tenders = []

    rows = soup.find_all("tr", id=re.compile(r"^A\d+"))
    print(f"  Строк с тендерами: {len(rows)}")

    for row in rows:
        tr_id = row.get("id", "")
        tender_id = tr_id.replace("A", "") if tr_id.startswith("A") else ""

        onclick = row.get("onclick", "")
        m = re.search(r"ShowApp\((\d+)", onclick)
        if m:
            tender_id = m.group(1)

        if not tender_id:
            continue

        cols = row.find_all("td")
        col_texts = [c.get_text(separator=" ", strip=True) for c in cols]

        name = ""
        for c in cols:
            txt = c.get_text(strip=True)
            if len(txt) > len(name) and not txt.startswith("NAT") and not txt.startswith("SPA"):
                name = txt

        reg_id = ""
        for txt in col_texts:
            if any(txt.startswith(p) for p in ["NAT", "SPA", "GEO", "CON", "MEP", "DAP"]):
                reg_id = txt
                break

        tender = {
            "id": tender_id,
            "reg_id": reg_id or (col_texts[0] if col_texts else ""),
            "name": name,
            "org": col_texts[2] if len(col_texts) > 2 else "",
            "date": col_texts[3] if len(col_texts) > 3 else "",
            "price": col_texts[4] if len(col_texts) > 4 else "",
            "deadline": col_texts[5] if len(col_texts) > 5 else "",
        }
        tenders.append(tender)
        print(f"  ✅ Найден: {tender['reg_id']} — {tender['name'][:60]}")

    return tenders

def save_to_csv(tender, label):
    exists = os.path.exists(SHEETS_FILE)
    with open(SHEETS_FILE, "a", encoding="utf-8-sig", newline="") as f:
        if not exists:
            f.write("Дата,ID,Номер,Название,Организация,Цена,Дедлайн,Категория,Ссылка\n")
        f.write(",".join([
            datetime.now().strftime("%d.%m.%Y"),
            tender.get("id", ""),
            tender.get("reg_id", ""),
            f'"{tender.get("name", "")}"',
            f'"{tender.get("org", "")}"',
            tender.get("price", ""),
            tender.get("deadline", ""),
            f'"{label}"',
            f'https://tenders.procurement.gov.ge/public/?lang=ru#go={tender.get("id", "")}'
        ]) + "\n")

def format_msg(tender, label):
    tid = tender.get("id", "")
    url = f"https://tenders.procurement.gov.ge/public/?lang=ru#go={tid}"
    return (
        f"🏋️ <b>НОВЫЙ ТЕНДЕР</b>\n"
        f"{'─' * 28}\n"
        f"📋 <b>{tender.get('reg_id', 'N/A')}</b>\n"
        f"📌 {tender.get('name', 'Без названия')[:100]}\n"
        f"🏢 {tender.get('org', '—')[:80]}\n"
        f"💰 {tender.get('price', '—')}\n"
        f"📅 Дедлайн: {tender.get('deadline', '—')}\n"
        f"🏷 {label}\n"
        f"🔗 <a href='{url}'>Открыть тендер</a>"
    )

def check_tenders():
    print(f"\n{'=' * 50}")
    print(f"[{datetime.now().strftime('%d.%m.%Y %H:%M')}] Проверяю тендеры...")

    seen = load_seen()
    new_count = 0

    for params in SEARCH_PARAMS:
        label = params["label"]
        print(f"\n  🔍 {label}...")
        tenders = search_tenders(params)

        for t in tenders:
            uid = t.get("id") or t.get("reg_id", "")
            if uid and uid not in seen:
                seen.add(uid)
                save_to_csv(t, label)
                send_telegram(format_msg(t, label))
                new_count += 1
                time.sleep(0.5)
        time.sleep(2)

    save_seen(seen)
    send_telegram(
        f"📊 Проверка {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        f"Новых тендеров: <b>{new_count}</b>"
    )
    print(f"\n✅ Готово! Новых тендеров: {new_count}")

if __name__ == "__main__":
    if not os.path.exists(SEEN_FILE):
        send_telegram("🤖 <b>Бот запущен!</b>\n✅ Мониторинг тендеров Грузии активен")
    check_tenders()
