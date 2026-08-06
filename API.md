# Karyer Local Server — Server API hujjati

Bu hujjat **server tomonini yozadigan dasturchi** uchun. Karyerdagi local
server (bu dastur) har bir tortish/o'tish hodisasini serverga yuboradi.
Server shu hodisalarni qabul qilib bazaga yozadi.

> ⚠️ **Eng muhim qoida:** local server internetni yo'qotsa yoki server javob
> bermasa, xuddi shu hodisani **qayta-qayta yuboradi** (ma'lumot yo'qolmasligi
> uchun). Shuning uchun server **`event_uid` bo'yicha dublikatni ajratishi shart**
> — aks holda bitta mashina bir necha marta hisoblanib qoladi. (2-bo'lim)

---

## 1. Umumiy

| | |
|---|---|
| Base URL | `http://SERVER_IP:PORT` (masalan `http://69.62.127.130:5555`) |
| Format | UTF-8 |
| Autentifikatsiya | Har so'rovda header: `X-API-Key: <kalit>` |
| Vaqt zonasi | `event_time` — O'zbekiston vaqti (UTC+5), `YYYY-MM-DD HH:MM:SS` |

---

## 2. Idempotency (dublikatni oldini olish) — MAJBURIY

Har bir hodisada noyob **`event_uid`** (UUID) bo'ladi. Bir hodisa bir necha
marta kelishi mumkin (retry). Server quyidagicha ishlashi kerak:

1. `event_uid` bazada **bor bo'lsa** → yangi yozuv yaratmaydi, `200 OK` qaytaradi
   (o'sha mavjud yozuv `id` si bilan). Ya'ni takror yuborish xavfsiz.
2. `event_uid` **yo'q bo'lsa** → yangi yozuv yaratadi.

`event_uid` ustuniga **UNIQUE** indeks qo'ying.

---

## 3. Endpointlar

### 3.1. `GET /api/ping` — ulanishni tekshirish
Local server ishga tushganda va vaqti-vaqti bilan chaqiradi.

**Javob (200):**
```json
{ "ok": true, "server_time": "2026-07-05 14:39:27" }
```

---

### 3.2. `POST /api/weigh` — asosiy hodisa (raqam + vazn + rasm + video)

Bitta mashina hodisasi. Local server **default holda Format B (multipart)** yuboradi
— rasm va video **faylning o'zi** ketadi. Format `config.server.send_files` bilan
tanlanadi (`true` = multipart, `false` = JSON). Serverда **Format B ni** qo'llang.

#### Format A — `application/json` (fayl yo'lsiz)
Faqat matnli ma'lumot. Rasm/video **yo'llari** yuboriladi (faqat `send_files:false` da).

```
POST /api/weigh
X-API-Key: <kalit>
Content-Type: application/json
```
```json
{
  "event_uid": "a3f1c2e4-5b6d-47a8-9c01-2d3e4f5a6b7c",
  "quarry_id": "KARYER-01",
  "camera_name": "ZAVOD-KIRISH",
  "is_main": true,
  "plate": "01S748HE",
  "direction": "in",
  "weight": 31200.0,
  "unit": "kg",
  "event_time": "2026-07-05 14:39:27",
  "video_path": "videos/zavod-1_01S748HE_20260705_143927.mp4",
  "image_paths": ["captures/zavod-1_01S748HE_20260705_143927_0.jpg"]
}
```

#### Format B — `multipart/form-data` (rasm + video fayl bilan) ✅ DEFAULT
Rasm va video faylning **o'zi** yuboriladi. Server fayllarni saqlab, URL qaytaradi.
Video 10s yozib olinadi — local server hodisani **video tayyor bo'lgach** yuboradi,
shuning uchun `video` part doim to'liq keladi.

```
POST /api/weigh
X-API-Key: <kalit>
Content-Type: multipart/form-data
```
| Part | Turi | Izoh |
|------|------|------|
| `data` | matn (JSON string) | Yuqoridagi JSON (fayl yo'llarsiz) |
| `images` | fayl (0..N ta) | ANPR kamera snapshotlari (jpg) |
| `video` | fayl (0..1 ta) | Video klip (mp4) |

`curl` namunasi:
```bash
curl -X POST http://SERVER:5555/api/weigh \
  -H "X-API-Key: SECRET" \
  -F 'data={"event_uid":"a3f1...","quarry_id":"KARYER-01","camera_name":"ZAVOD-KIRISH","is_main":true,"plate":"01S748HE","weight":31200,"unit":"kg","event_time":"2026-07-05 14:39:27"};type=application/json' \
  -F 'images=@snap0.jpg' \
  -F 'video=@clip.mp4'
```

#### Muvaffaqiyatli javob (200 yoki 201):
```json
{ "ok": true, "id": 12345, "event_uid": "a3f1c2e4-...", "trip_id": "7b0e..." }
```
- `id` — serverdagi yozuv identifikatori.
- Local server `2xx` ni "yuborildi" deb qabul qiladi va navbatdan o'chiradi.
- **`2xx` bo'lmasa** — local server keyinroq qayta yuboradi.

---

## 4. Payload maydonlari

| Maydon | Turi | Majburiy | Izoh |
|--------|------|:---:|------|
| `event_uid` | string (UUID) | ✅ | Idempotency kaliti. UNIQUE. |
| `quarry_id` | string | ✅ | Karyer identifikatori. |
| `camera_name` | string | ✅ | Kamera nomi — stansiyalarni shu orqali ajratiladi. |
| `is_main` | bool | ✅ | **`true`** = asosiy zavod (tarozili). **`false`** = kon (raqam + video, vaznsiz). |
| `plate` | string / null | ⛔ | Davlat raqami (masalan `01S748HE`). Aniqlanmasa `null`. |
| `direction` | string / null | ⛔ | **`"in"`** = kirish, **`"out"`** = chiqish, `null` = raqam aniqlanmagan. |
| `weight` | number / null | ⛔ | Vazn (kg). Kon'da (is_main=false) odatda `null`. |
| `unit` | string | ✅ | Doim `"kg"`. |
| `event_time` | string | ✅ | UTC+5, `YYYY-MM-DD HH:MM:SS`. |
| `video_path` | string / null | ⛔ | A formatda yo'l; B formatda `video` part. Kon'da ham video keladi. |
| `image_paths` | string[] | ⛔ | A formatda yo'llar; B formatda `images` partlar. |

### `is_main` semantikasi
- **`is_main: true`** — asosiy zavod tarozisi: raqam **+ vazn + video** keladi.
- **`is_main: false`** — kon nazorat nuqtasi: **raqam + rasm + video**, vazn yo'q
  (`weight: null`). Video mexanizmi zavod bilan bir xil — mashina zonaga
  kirishi bilan klip yoziladi, yo'nalish videodan aniqlanadi.

### `direction` semantikasi (kirish/chiqish)
Bitta darvoza/tarozidan mashina **ham kiradi, ham chiqadi**. Yo'nalish ikki
usulda aniqlanadi (ustuvorlik tartibida):

1. **Video zona (zavod va kon, asosiy usul):** video kamerada chizilgan zonaga
   mashina **qaysi tomondan kirgani** (KIRISH tomoni yoki CHIQISH tomoni)
   YOLO bilan aniqlanadi — fizik harakat yo'nalishi. Mashina zonaga kirishi
   bilan video yozish ham shu paytdan boshlanadi (klip mashinaning kelishini
   to'liq qamrab oladi). Raqamsiz mashinada ham ishlaydi.
2. **Raqam almashinuvi (zaxira):** birinchi ko'rinish → `"in"`,
   keyingisi → `"out"`, almashinib boradi. Oxirgi harakatdan **N soat**
   (default 12) o'tsa hisob tozalanib yana `"in"`. Video usul ishlaganda bu
   hisob ham unga moslab sinxronlanadi.
- Raqam ham, video yo'nalish ham yo'q bo'lsa → `direction: null`.

Server har hodisani alohida yozadi — `in`/`out` juftliklari orqali mashinaning
ichкarida qancha turgani, necha qatnov qilgani hisoblab chiqiladi.

---

## 5. Xato javoblari

| HTTP | Holat | Local server nima qiladi |
|------|-------|--------------------------|
| `200/201` | Muvaffaqiyat | Navbatdan o'chiradi ✅ |
| `401/403` | API kalit noto'g'ri | Qayta urinadi (kalitni tekshiring) |
| `400` | Payload xato | Qayta urinadi — server logi bilan tekshiring |
| `409` | `event_uid` allaqachon bor | **`200` kabi** qabul qilinsa yaxshi (dublikat = muvaffaqiyat) |
| `5xx` / timeout / ulanmadi | Server/tarmoq muammosi | Backoff bilan qayta-qayta yuboradi |

Xato javob tanasi (ixtiyoriy):
```json
{ "ok": false, "error": "sabab matni" }
```

**Retry jadvali (local server):** 5s → 10s → 20s → 40s → 80s → 160s → 300s
(maksimum 5 daqiqa), server tiklanguncha to'xtamaydi.

---

## 6. Server tomon uchun tavsiyalar

1. **Jadval (taxminiy):**
   ```sql
   CREATE TABLE weigh_events (
     id           BIGSERIAL PRIMARY KEY,
     event_uid    UUID UNIQUE NOT NULL,   -- idempotency
     quarry_id    TEXT NOT NULL,
     camera_name  TEXT NOT NULL,
     is_main      BOOLEAN NOT NULL,
     plate        TEXT,
     weight       NUMERIC,
     unit         TEXT DEFAULT 'kg',
     event_time   TIMESTAMP,              -- UTC+5
     video_url    TEXT,
     image_urls   TEXT[],                 -- yoki JSON
     received_at  TIMESTAMP DEFAULT now()
   );
   ```
2. Fayllarni (rasm/video) diskda yoki S3'da saqlab, `video_url`/`image_urls` ga
   URL yozing.
3. `X-API-Key` ni har karyer uchun alohida bering (kim yuborayotganini bilish uchun).
4. Katta video uchun so'rov hajmi limitini oshiring (masalan 100 MB).
5. Javobni **tez** qaytaring — fayllarni fon rejimida qayta ishlash mumkin,
   lekin `2xx` ni qabul qilgandan keyin bering (aks holda local server qayta yuboradi).

---

## 7. Local server sozlamasi (mijoz tomoni)
`config.json → server`:
```json
{
  "server": {
    "url": "http://69.62.127.130:5555",
    "api_key": "KARYER-01-SECRET",
    "enabled": true,
    "endpoint": "/api/weigh"
  }
}
```
`enabled: true` bo'lganda yuborish boshlanadi. Endpoint sozlanadi.

---

## 8. Hozirgi holat / kelishuv kerak
- ✅ Payload shakli tayyor (yuqoridagi).
- ✅ Local server **multipart bilan rasm + video faylni yuboradi** (default, sinovdan o'tgan).
- ✅ Rasm/video **yuborishdan oldin siqiladi** (rasm ~80% kichrayadi; video ffmpeg bo'lsa H.264).
- ✅ Video tayyor bo'lgachgina yuboradi; `event_uid` idempotency; retry backoff.
- ⏳ **Kelishuv:** fayllarni server diskda saqlaydimi yoki S3'da? Maksimal so'rov hajmi?
- ⏳ Server URL, API kalit, port — server tayyor bo'lgach `config.json`ga yoziladi.
