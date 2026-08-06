# Karyer Local Server

Karyerdan chiqayotgan yukni hisoblash: **raqam (ANPR) + vazn (KELI D12) + video**
→ real vaqtda serverga (uzilsa — qayta-qayta urinadi, ma'lumot yo'qolmaydi).
To'liq TZ: [TZ.md](TZ.md)

## O'rnatish (Windows 10/11)
```
pip install -r requirements.txt
```

## Ishlash modeli — FON (tray) xizmati
Dastur soat yonidagi **ikonka** sifatida fonda ishlaydi (oyna ochilmaydi).
Ikonkani **o'ng tugma** bilan bosib boshqarasiz:

| Menyu | Nima qiladi |
|-------|-------------|
| ● Ishlayapti — N stansiya · navbat: P | joriy holat |
| Sozlamalarni tahrirlash | Setup oynasi; **saqlangach dastur avtomatik qayta ishga tushadi** |
| Qayta ishga tushirish | stansiyalarni qayta yoqadi |
| Rasm/videolar papkasi | saqlangan fayllar papkasini ochadi |
| Chiqish | fon xizmatini butunlay to'xtatadi |

> Ikonkaga **ikki marta** bossangiz ham Sozlash oynasi ochiladi.

## O'rnatish — BITTA fayl hamma narsani qiladi ⭐
Faqat **`boshlash.py`** ni ishga tushiring (yoki **`Karyer Server.bat`** ni ikki marta bosing):
```
python boshlash.py
```
U avtomatik:
1. Kerakli kutubxonalarni **o'rnatadi** (yo'qlarini)
2. **Avtomatik ishga tushirishni yoqadi** (kompyuter yoqilganda o'zi ishlaydi)
3. Dasturni ishga tushiradi:
   - **birinchi marta** → Sozlash oynasi (parolsiz) → Quarry ID, stansiyalar, kamera/tarozi/zona → Saqlash → fon rejim
   - **keyingi safar** → to'g'ridan-to'g'ri fon (tray) rejim

Avtomatik ishga tushirishni o'chirish: **`uninstall_autostart.bat`**.

## Parol
Sozlamalarni **tahrirlash** uchun parol so'raladi: **`!QAZ`**
(Birinchi o'rnatishda parol so'ralmaydi.)

## Buyruqlar (qo'lda)
| Buyruq | Nima qiladi |
|--------|-------------|
| `python main.py` | config bo'lsa **fon (tray)** rejimida; bo'lmasa Setup ochiladi |
| `python main.py --setup` | Setup oynasini ochish (tahrirlash) |
| `python main.py --console` | tray'siz, terminalда ishlash (Ctrl+C bilan to'xtatish) |
| `python main.py --sim` | **apparatsiz test** — soxta tarozi + ANPR |
| `python main.py --provision <TOKEN>` | **token bilan serverdan sozlash** — quarry_id, api_key, server URL ni avtomatik oladi (web-main'dagi kalit tugmasidan token). Setup oynasida ham "Serverdan olish" tugmasi bor. |
| `python scale_capture.py` | tarozi (COM port) xom ma'lumotini ko'rish |

## Tahrirlash (dastur ishlab turганda)
Fon ikonkasi → **Sozlamalarni tahrirlash** → o'zgartiring → **Saqlash**.
Dastur yangi sozlamalar bilan **o'zi qayta ishga tushadi**, qo'lda restart shart emas.

## Fayllar
```
boshlash.py        ⭐ HAMMASINI avtomatik: o'rnatish + avtostart + ishga tushirish
main.py            kirish nuqtasi (tray / setup / console / sim)
tray.py            FON xizmati — soat yonidagi ikonka + menyu
manager.py         stansiyalarni start/stop/restart boshqaruvi
setup_gui.py       sozlash oynasi + zona/yo'nalish chizish (PyQt6)
icons.py           yagona SVG ikonkalar
station.py         KON / ZAVOD stansiya mantig'i (hodisa yig'ish)
detector.py        YOLO zona detektori (yo'nalish + video trigger)
anpr_listener.py   Dahua ANPR hodisa tinglovchisi
scale/             tarozi: serial (KELI D12), simulyator, MODE-stabilizator
video_recorder.py  RTSP dan N soniya klip yozish
media.py           rasm/video siqish (compress)
outbox.py          serverga ishonchli yuborish (backoff retry)
api_client.py      server API (multipart: rasm+video fayl)
db.py              SQLite: weigh_events + outbox + vehicle_state
config.py          config.json o'qish/yozish, defaultlar
scale_capture.py   KELI D12 formatini aniqlash vositasi
*.bat              Windows: ishga tushirish / sozlash / avtostart
```

## Holat
- ✅ Bosqich 1: poydevor — simulyator bilan uchidan-uchiga ishlaydi
- ✅ Bosqich 2: real KELI D12 ulangan (COM, STX/ETX frame). DIQQAT: indikator
  parity'si EvEn bo'lsa config'da `scale.bytesize: 7, scale.parity: "E"` (7E1)
  qilinishi shart — 8N1 bilan baytlar buziladi. Default 8N1 (nonE).
- ✅ Bosqich 3: server API ishlayapti (`/api/weigh`, X-API-Key, outbox retry)

## Live (jonli ko'rish) — hozircha O'CHIQ
`heartbeat.py` + `live_manager.py` — server orqali jonli ko'rish (snapshot yoki
MediaMTX video push). Server tomonida `/api/local/heartbeat` va
`/api/local/live-snapshot` endpointlari tayyor bo'lgach `config.json`ga:
```json
"live": { "enabled": true, "heartbeat_interval_s": 15 }
```
qo'shiladi (default o'chiq — yoqilmaguncha bu modullar umuman ishlamaydi).
Buyruqlar heartbeat JAVOBIDA keladi (localga tashqaridan kirish yo'q):
server so'ragan kamera uchun TTL bilan sessiya ochiladi — snapshot rejimda
detektorning tayyor JPEG buferidan kadr yuboriladi (yangi RTSP sessiyasiz),
video rejimda ffmpeg SUB-oqimni `-c copy` bilan push qiladi. Hodisa navbati
bo'sh bo'lmaguncha live to'xtab turadi (hodisa > jonli — o'zgarmas qoida).
To'liq loyiha: `..\MUVOFIQLIK-VA-LIVE-STREAM.md`
