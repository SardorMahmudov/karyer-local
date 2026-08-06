# Texnik topshiriq — Karyer Local Server

## 1. Maqsad
Karyerlardan qancha yuk chiqib ketayotganini avtomatik hisoblash.
Har bir mashina uchun: **davlat raqami + vazn + vaqt + rasm/video** yig'iladi
va **real vaqtda serverga** yuboriladi.

## 2. Ish rejimlari (config'dan tanlanadi)

### KON rejimi — mustaqil (yakka)
- Faqat **1 ta ANPR kamera**.
- Mashina o'tganda: `{quarry_id, raqam, vaqt, rasm}` → serverga.
- Tarozi va video **yo'q**. Zavodga bog'liq emas, alohida ishlaydi.

### ZAVOD rejimi — tarozi + video + ANPR hamohang
- **1 ANPR kamera + 1 video kamera + 1 tarozi (KELI D12)**.
- Oqim:
  1. Mashina belgilangan **zonaga kiradi** (video kamerada aniqlanadi).
  2. Mashina **to'liq taroziga chiqqani** tasdiqlanadi (5-bo'limga qarang).
  3. **Tarozi** barqaror vaznni beradi (5-bo'lim: mode algoritmi).
  4. **ANPR kamera** raqamni beradi.
  5. Video kamera **klip yozadi** (uzunligi sozlanadigan, default 10s).
  6. Hammasi vaqt bo'yicha **bitta hodisaga** bog'lanadi:
     `{quarry_id, raqam, vazn, vaqt, video, rasmlar}` → serverga.
- Video trigger: **zona + tarozi ikkalasi tasdiqlaganda**.

## 4a. Mashina taroziga chiqqanini tasdiqlash va barqaror vaznni olish
Mashina taroziga chiqqanda **silkinish** tufayli raqamlar bir muddat
tez-tez o'zgaradi. Shuning uchun:

1. **To'liq chiqqanini tasdiqlash:** vazn belgilangan **chegaradan**
   (`min_weight`) oshib, **bir necha soniya** shu chegaradan yuqorida
   turishi kerak (bitta o'q o'tishi emas, mashina to'liq turishi).
2. **Barqarorlik:** har bir vazn o'zgarishi o'qib boriladi; qiymatlar
   `stability_tolerance` (masalan ±20 kg) ichida `settle_time` davomida
   turg'un bo'lsa — barqaror deb hisoblanadi.
3. **Yakuniy vazn = MODE:** barqarorlik oynasidagi barcha o'qilgan
   qiymatlar orasidan **eng ko'p takrorlangan (mode)** kilogramm olinadi.
   Bu silkinish sabab noto'g'ri qiymatlarni chetlab o'tadi.
4. Mashina tarozidan tushsa (vazn `min_weight` dan pastga) — hodisa yakunlanadi.

**Sozlanadigan parametrlar (config'da):**
- `min_weight` — mashina bor deb hisoblash chegarasi (kg)
- `settle_time` — barqarorlik uchun kutish vaqti (s)
- `stability_tolerance` — ruxsat etilgan tebranish (±kg)
- `capture_duration` — video klip uzunligi (s, o'zgartiriladi)
- `capture_delay` — klip qachon boshlanishi (s, o'zgartiriladi)

## 3. Apparat
| Qurilma | Ulanish |
|---------|---------|
| Tarozi indikatori **KELI D12** | RS-232 (DB9 "PC接口") → **USB-RS232 adapter** (FTDI/CH340), 9600 8N1, continuous rejim |
| ANPR kamera (Dahua / Hikvision) | Tarmoq (HTTP event stream) — raqamni kameraning o'zi beradi |
| Video kamera (Dahua / Hikvision) | RTSP main stream |
| Kompyuter | Windows 10/11 |

## 4. Ma'lumotni serverga yuborish (ishonchli sync)
- Har bir hodisa avval lokal **SQLite outbox**ga `pending` bilan yoziladi.
- Fon oqimi serverga yuboradi; muvaffaqiyatli → `sent`.
- Xato (internet/server o'chiq) bo'lsa — **backoff bilan qayta-qayta urinadi**, ma'lumot yo'qolmaydi.
- Server API hali kelishilmagan → o'zimizning toza JSON sxemamiz, server URL config'da.

## 5. Interfeys
- Oddiy ishda **oyna yo'q** — fon xizmati sifatida ishlaydi.
- **Setup oynasi** faqat sozlash uchun ochiladi:
  - quarry_id, rejim, kameralar, tarozi sozlamalari;
  - **zona/chiziq chizish** (mashina qayerga kelganda video olinishi).
- Keyin fonda ishlaydi; kerak bo'lsa Setup'ni qayta ochib **tahrirlash** mumkin.

## 6. Raqam manbai
- Faqat **ANPR kameradan (hardware)** — vaqt bo'yicha tarozi/video bilan bog'lanadi.
- (Keyinchalik: video'dan software OCR — zaxira sifatida qo'shsa bo'ladi.)

## 7. Mavjud koddan foydalanish
`car_gate_pro.py` dan olinadi: setup GUI (zona/chiziq/kamera dialoglari),
YOLO detektor (zona triggeri), SQLite baza asosi.
`dahua_anpr_listener.py` dan: ANPR hodisa tinglovchisi.
Yangidan yoziladi: tarozi drayveri, video klip yozish, hodisa bog'lash (correlator),
outbox + retry.

## 8. Bosqichlar
1. **Bosqich 1 — poydevor:** papka tuzilishi, config, Setup GUI + zona chizish,
   ANPR integratsiyasi, outbox + retry, simulyator tarozi bilan uchidan-uchiga test.
2. **Bosqich 2 — real tarozi:** KELI D12 serial drayveri (formatni capture'dan aniqlab).
3. **Bosqich 3 — server:** API sxemasi kelishilgach ulanadi, kerak bo'lsa video yuklash.

## 9. Hozirgi holat
- ✅ Tarozi aniqlandi: KELI D12, RS-232.
- ✅ `scale_capture.py` yozildi — tarozi formatini aniqlash uchun.
- ⏳ Kutilmoqda: USB-RS232 adapter → capture natijasi → Bosqich 1 boshlanadi.
