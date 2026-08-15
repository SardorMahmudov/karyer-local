# Yangi karyerga o'rnatish

Bu qo'llanma dasturni **yangi kompyuterga** o'rnatish uchun. Taxminan 30-40 daqiqa.

---

## ⚠️ MUHIM: repoda YO'Q ikkita narsa

`git clone` faqat **kodni** beradi. Quyidagilar hajmi katta bo'lgani uchun repoga
qo'shilmagan — ularni **qo'lda ko'chirish** kerak (flashka yoki AnyDesk orqali):

| Nima | Hajmi | Kerakmi | Bo'lmasa nima bo'ladi |
|---|---|---|---|
| `ffmpeg/` papkasi | ~140 MB | **SHART** | Video umuman yozilmaydi (Karyer pre-roll), yoki brauzer o'ynatmaydi |
| `yolov8n.pt` | ~6 MB | Tavsiya | Internet bo'lsa dastur o'zi yuklab oladi; internetsiz — zona detektori ishlamaydi |

Ikkalasini ham **ishlayotgan kompyuterdagi `local` papkasidan** olib, yangi
kompyuterdagi `local` papkasiga (kod fayllari yoniga) qo'ying.

---

## Qadamlar

### 1. Python o'rnatish

[python.org](https://www.python.org/downloads/) — **Python 3.13**.

> O'rnatishda **"Add python.exe to PATH"** katagini belgilash **SHART**.

### 2. Kodni yuklab olish

```
git clone https://github.com/SardorMahmudov/karyer-local.git
```

(Git bo'lmasa: GitHub sahifasidan **Code → Download ZIP** qilib, arxivni oching.)

### 3. ffmpeg va YOLO modelini ko'chirish

Yuqoridagi jadvaldagi `ffmpeg/` papkasi va `yolov8n.pt` faylini shu papkaga
(`main.py` yonига) ko'chiring. Natijada shunday bo'lishi kerak:

```
karyer-local/
  ├─ main.py, station.py, ...
  ├─ ffmpeg/ffmpeg.exe      ← ko'chirilgan
  └─ yolov8n.pt             ← ko'chirilgan
```

### 4. Serverda karyerni sozlash va token olish

`web-main` saytida:
1. Yangi **karyer** yarating (yoki mavjudini oching)
2. **Post** qo'shing (masalan "Zavod" yoki "Karyer nazorat")
3. Postga **kameralarni** kiriting — har biriga: brend (dahua/hikvision),
   **IP manzil, login, parol**, va turi (`plate` = raqam o'qish, `record` = video)
4. Karyer sahifasidagi **kalit tugmasi** orqali **provisioning tokenini** oling

### 5. Sozlamalarni serverdan olish

Yangi kompyuterda, `local` papkasida:

```
python main.py --provision <TOKEN>
```

Bu `config.json` faylini avtomatik yaratadi: karyer ID, api_key, server manzili,
kameralar (IP/login/parol) — hammasi serverdan keladi.

### 6. Qo'lda sozlash (zona va tarozi)

```
Sozlash.bat
```

Parol: `!QAZ`

Bu yerda:
- **Tarozi** — COM portini tanlang (Qurilma menejeridan qaysi COM ekanini biling).
  Tarozi yo'q bo'lsa `weight_source` ni `none` qoldiring.
- **Zona va yo'nalishni chizish** — video kamera kadrida yo'l ustiga ko'pburchak
  chizing, so'ng KIRISH (yashil) va CHIQISH (qizil) tomonlarini belgilang.

### 7. Ishga tushirish

```
python boshlash.py
```

Bu o'zi: kerakli kutubxonalarni o'rnatadi (birinchi safar **~2-3 GB** yuklaydi,
internetga bog'liq 10-30 daqiqa), avtomatik ishga tushishni yoqadi va dasturni
fon (tray) rejimida ishga tushiradi.

### 8. Avtomatik kirishni yoqish (tok o'chib-yonganda)

Windows qidiruvida `netplwiz` → foydalanuvchini tanlang → **"Требовать ввод
имени пользователя и пароля"** katagini **olib tashlang** → parolni kiriting.

Shunda tok o'chib-yonganda Windows o'zi kiradi va dastur o'zi ko'tariladi.

### 9. Tekshirish

```
Holat.bat
```

Hammasi **yashil** bo'lishi kerak: dastur ishlayapti, kameralar javob beryapti,
COM port bor, avtomatik ishga tushish yoqilgan.

> Kompyuter yangi yonganda YOLO yuklanishi uchun ~1 daqiqa kutib tekshiring.

---

## Keyinchalik yangilash

Kod yangilanganda, shu papkada:

```
git pull
```

so'ng dasturni qayta ishga tushiring (tray ikonkasidan chiqib, `boshlash.py`ni
qayta oching). `config.json`, baza va videolar **o'z joyida qoladi** — ular
repoga kirmaydi, `git pull` ularga tegmaydi.

---

## Muammolar

| Belgi | Sabab / davo |
|---|---|
| Video kelmayapti | `ffmpeg/ffmpeg.exe` joyidami? (3-qadam) |
| Yo'nalish har doim noma'lum | Zona chizilmagan (6-qadam) yoki `yolov8n.pt` yo'q |
| Kamera ulanmayapti | IP/parolni tekshiring; kamerani ping qiling |
| Dastur ikki marta ochilgan | Ochilmaydi — bitta nusxa qulfi bor (bu normal) |
| Hodisalar serverga ketmayapti | Internetni tekshiring; ular navbatda saqlanadi va aloqa tiklanganda o'zi jo'naydi |

Tashxis fayllari (`link_debug.log`, `video_debug.log`, `det_debug.log`,
`anpr_debug.log`) shu papkada hosil bo'ladi — muammoni aniqlashda yordam beradi.
