import requests
import json
import os
import time
import re
from datetime import datetime
from bs4 import BeautifulSoup

TELEGRAM_BOT_TOKEN = "8728034905:AAG8AfIziMpCst9jUo1iQJM0FV6YUrQjSSk"
TELEGRAM_CHAT_ID   = "1656687130"

SEEN_FILE    = "seen_tenders.json"
TRACKED_FILE = "tracked_tenders.json"
SHEETS_FILE  = "tenders.csv"

SEARCH_PARAMS = [
    {"app_basecode": "18999", "app_codes": "", "label": "45100000 - Подготовка стройплощадки"},
    {"app_basecode": "18951", "app_codes": "", "label": "37400000 - Спортивные товары"},
    {"app_basecode": "18965", "app_codes": "", "label": "37500000 - Игры и аттракционы"},
    {"app_basecode": "0", "app_codes": "37420000", "label": "CPV 37420000 - Гимнастика"},
    {"app_basecode": "0", "app_codes": "37440000", "label": "CPV 37440000 - Фитнес"},
    {"app_basecode": "0", "app_codes": "45112700", "label": "CPV 45112700 - Ландшафт"},
    {"app_basecode": "0", "app_codes": "45112720", "label": "CPV 45112720 - Ландшафт спортплощадок"},
]

STATUS_EMOJI = {
    "Объявлен": "🆕",
    "Приём предложений начался": "📨",
    "Приём предложений завершён": "📭",
    "Отбор/оценка": "🔍",
    "Победитель выявлен": "🏆",
    "Завершён с отрицательным результатом": "❌",
    "Не состоялся": "⚠️",
    "Прекращён": "🚫",
    "Идёт подготовка договора": "📝",
    "Договор подписан": "✅",
}

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False)

def load_tracked():
    if os.path.exists(TRACKED_FILE):
        with open(TRACKED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_tracked(tracked):
    with open(TRACKED_FILE, "w", encoding="utf-8") as f:
        json.dump(tracked, f, ensure_ascii=False, indent=2)

def send_telegram(msg):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=15
        )
        return r.status_code == 200
    except Exception as e:
        print(f"  Telegram hata: {e}")
        return False

def get_session():
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
    return session

def search_tenders(params):
    session = get_session()
    data = {
        "action": "search_app", "app_t": "0", "search": "1",
        "app_reg_id": "", "app_shems_id": "0", "org_a": "",
        "app_monac_id": "0", "org_b": "", "app_particip_status_id": "0",
        "app_donor_id": "0", "app_status": "10", "app_agr_status": "0",
        "app_type": "0",
        "app_basecode": params.get("app_basecode", "0"),
        "app_codes": params.get("app_codes", ""),
        "app_date_type": "1", "app_date_from": "", "app_date_tlll": "",
        "app_amount_from": "", "app_amount_to": "",
        "app_currency": "2", "app_pricelist": "0",
    }
    try:
        r = session.post(
            "https://tenders.procurement.gov.ge/public/library/controller.php",
            data=data, timeout=30
        )
        if r.status_code == 200 and len(r.text) > 100:
            return parse_list_html(r.text)
    except Exception as e:
        print(f"  Hata: {e}")
    return []

def parse_list_html(html):
    soup = BeautifulSoup(html, "html.parser")
    tenders = []
    rows = soup.find_all("tr", id=re.compile(r"^A\d+"))
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
            if len(txt) > len(name) and not any(txt.startswith(p) for p in ["NAT","SPA","GEO","CON","MEP","DAP"]):
                name = txt
        reg_id = ""
        for txt in col_texts:
            if any(txt.startswith(p) for p in ["NAT","SPA","GEO","CON","MEP","DAP"]):
                reg_id = txt
                break
        tenders.append({
            "id": tender_id,
            "reg_id": reg_id or (col_texts[0] if col_texts else ""),
            "name": name,
            "org": col_texts[2] if len(col_texts) > 2 else "",
            "price": col_texts[4] if len(col_texts) > 4 else "",
            "deadline": col_texts[5] if len(col_texts) > 5 else "",
        })
    return tenders

def get_tender_detail(tender_id):
    session = get_session()
    try:
        r = session.post(
            "https://tenders.procurement.gov.ge/public/library/controller.php",
            data={"action": "get_app", "app_id": tender_id, "go": tender_id},
            timeout=30
        )
        if r.status_code == 200 and len(r.text) > 100:
            detail = parse_detail_html(r.text)
            if detail.get("status"):
                return detail
    except:
        pass
    try:
        r2 = session.get(
            f"https://tenders.procurement.gov.ge/public/?lang=ru&go={tender_id}",
            timeout=30
        )
        if r2.status_code == 200:
            return parse_detail_html(r2.text)
    except:
        pass
    return {}

def parse_detail_html(html):
    detail = {}
    for status_key in STATUS_EMOJI.keys():
        if status_key in html:
            detail["status"] = status_key
            break
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["td", "div", "span"]):
        txt = tag.get_text(strip=True)
        if "Победитель" in txt:
            nxt = tag.find_next("td") or tag.find_next("span")
            if nxt:
                w = nxt.get_text(strip=True)
                if w and w != txt:
                    detail["winner"] = w[:100]
    m = re.search(r"Количество участников[^\d]*(\d+)", html)
    if m:
        detail["participants"] = m.group(1)
    return detail

def format_new_msg(tender, label):
    tid = tender.get("id", "")
    url = f"https://tenders.procurement.gov.ge/public/?lang=ru&go={tid}"
    return (
        f"🆕 <b>YENİ TENDER</b>\n"
        f"{'─'*28}\n"
        f"📋 <b>{tender.get('reg_id','N/A')}</b>\n"
        f"📌 {tender.get('name','')[:100]}\n"
        f"🏢 {tender.get('org','—')[:80]}\n"
        f"💰 {tender.get('price','—')}\n"
        f"📅 Son tarih: {tender.get('deadline','—')}\n"
        f"🏷 {label}\n"
        f"🔗 <a href='{url}'>Tenderi aç</a>"
    )

def format_status_msg(tid, reg_id, name, old_s, new_s, detail):
    url = f"https://tenders.procurement.gov.ge/public/?lang=ru&go={tid}"
    emoji = STATUS_EMOJI.get(new_s, "📌")
    msg = (
        f"{emoji} <b>DURUM DEĞİŞTİ</b>\n"
        f"{'─'*28}\n"
        f"📋 <b>{reg_id}</b>\n"
        f"📌 {name[:80]}\n\n"
        f"<b>Eski:</b> {old_s}\n"
        f"<b>Yeni:</b> {new_s}\n"
    )
    if detail.get("winner"):
        msg += f"\n🏆 <b>Kazanan:</b> {detail['winner']}\n"
    if detail.get("participants"):
        msg += f"👥 <b>Katılımcı:</b> {detail['participants']}\n"
    msg += f"\n🔗 <a href='{url}'>Tenderi aç</a>"
    return msg

def save_to_csv(tender, label):
    exists = os.path.exists(SHEETS_FILE)
    with open(SHEETS_FILE, "a", encoding="utf-8-sig", newline="") as f:
        if not exists:
            f.write("Tarih,ID,Numara,Isim,Organizasyon,Fiyat,Son Tarih,Kategori,Link\n")
        f.write(",".join([
            datetime.now().strftime("%d.%m.%Y"),
            tender.get("id",""), tender.get("reg_id",""),
            f'"{tender.get("name","")}"', f'"{tender.get("org","")}"',
            tender.get("price",""), tender.get("deadline",""),
            f'"{label}"',
            f'https://tenders.procurement.gov.ge/public/?lang=ru&go={tender.get("id","")}'
        ]) + "\n")

def check_new_tenders(seen, tracked):
    print("\n📋 Yeni tender aranıyor...")
    new_count = 0
    for params in SEARCH_PARAMS:
        label = params["label"]
        print(f"  🔍 {label}...")
        tenders = search_tenders(params)
        print(f"  Bulunan: {len(tenders)}")
        for t in tenders:
            uid = t.get("id") or t.get("reg_id","")
            if uid and uid not in seen:
                seen.add(uid)
                save_to_csv(t, label)
                send_telegram(format_new_msg(t, label))
                tracked[uid] = {
                    "reg_id": t.get("reg_id",""),
                    "name": t.get("name",""),
                    "status": "Объявлен",
                    "label": label,
                    "added": datetime.now().strftime("%d.%m.%Y"),
                }
                new_count += 1
                print(f"  ✅ {t.get('reg_id')} — {t.get('name','')[:50]}")
                time.sleep(0.5)
        time.sleep(2)
    return new_count

def check_tracked_statuses(tracked):
    if not tracked:
        print("\n📌 Takip edilen tender yok.")
        return 0
    print(f"\n📌 {len(tracked)} tender kontrol ediliyor...")
    changed = 0
    for tid, info in list(tracked.items()):
        print(f"  {info.get('reg_id', tid)}...", end=" ")
        detail = get_tender_detail(tid)
        new_s = detail.get("status","")
        if not new_s:
            print("bulunamadı")
            time.sleep(2)
            continue
        old_s = info.get("status","")
        if new_s != old_s:
            print(f"DEĞİŞTİ! {old_s} → {new_s}")
            tracked[tid]["status"] = new_s
            send_telegram(format_status_msg(
                tid, info.get("reg_id",""), info.get("name",""),
                old_s, new_s, detail
            ))
            changed += 1
        else:
            print(f"aynı ({new_s})")
        time.sleep(2)
    return changed

def check_tenders():
    print(f"\n{'='*50}")
    print(f"[{datetime.now().strftime('%d.%m.%Y %H:%M')}] Kontrol başlıyor...")
    seen = load_seen()
    tracked = load_tracked()
    new_count = check_new_tenders(seen, tracked)
    changed_count = check_tracked_statuses(tracked)
    save_seen(seen)
    save_tracked(tracked)
    send_telegram(
        f"📊 Kontrol: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        f"🆕 Yeni tender: <b>{new_count}</b>\n"
        f"🔄 Durum değişimi: <b>{changed_count}</b>\n"
        f"📌 Takip edilen: <b>{len(tracked)}</b>"
    )
    print(f"\n✅ Bitti! Yeni: {new_count}, Değişen: {changed_count}")

if __name__ == "__main__":
    if not os.path.exists(SEEN_FILE):
        send_telegram("🤖 <b>Bot başlatıldı!</b>\n✅ Gürcistan tender takibi aktif")
    check_tenders()
