#!/usr/bin/env python3
"""
ANPR kamera tinglovchisi (Dahua / Hikvision).

Kamera bilan ochiq HTTP ulanish o'rnatadi va raqam aniqlanganda
on_plate(plate, images, ts) callback'ni chaqiradi. Ulanish uzilsa qayta ulanadi.

Sim rejim (kamera IP yo'q) — test uchun soxta raqamlar generatsiya qiladi.
"""

import re
import time
import random
import threading
import datetime

try:
    import requests
    from requests.auth import HTTPDigestAuth
except ImportError:
    requests = None

EVENTS = "[All]"


class AnprListener:
    def __init__(self, anpr_cfg, on_plate, name="ANPR", sim=False):
        self.cfg = anpr_cfg
        self.on_plate = on_plate          # callback(plate:str, images:list[bytes], ts:float)
        self.name = name
        self.sim = sim or not anpr_cfg.get("ip")
        # aktiv snapshot: raqam kelib rasm bo'lmasa kameradan joriy kadrni
        # o'zi tortadi. Zavod kamerasi tez (~0.5s) — foydali. Karyer kamerasi
        # sekin (~15-18s) — mashina ketib bo'ladi, BO'SH YO'L keladi; u yerda
        # o'chiriladi (station detektor bufferidan aniq kadr oladi).
        self.active_snapshot = anpr_cfg.get("active_snapshot", True)
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._last_emit_plate = ""    # oxirgi yuborilgan raqam (ko'p-snapshot dedup)
        self._last_emit_ts = 0.0
        # Oxirgi yuborilgan hodisaning images-LISTI (reference!). Dahua katta
        # rasmni (0.6-1MB) raqamdan 10-60s KEYIN yuboradi — raqam darhol
        # yuboriladi (bo'sh list bilan), kech kelgan rasm shu listga qo'shiladi;
        # stansiya buferi/late-watcher'da ham AYNI SHU list turadi, shuning uchun
        # rasm o'z hodisasiga yetib boradi (outbox rasmni ~100s kutadi).
        self._last_emit_images = None

    def start(self):
        self._running = True
        target = self._run_sim if self.sim else self._run_real
        self._thread = threading.Thread(target=target, name=f"anpr-{self.name}", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    # ---------- SIM ----------
    def _run_sim(self):
        rng = random.Random()
        regions = ["01", "10", "30", "40", "50", "90"]
        letters = "ABCDEFGHJKLMNPQRSTUVXYZ"
        print(f"[{self.name}] SIM rejim — soxta raqamlar")
        while self._running:
            time.sleep(rng.uniform(3, 6))
            if not self._running:
                return
            plate = f"{rng.choice(regions)}{rng.choice(letters)}{rng.randint(100,999)}{rng.choice(letters)}{rng.choice(letters)}"
            self.on_plate(plate, [], time.time())

    # ---------- REAL ----------
    def _url(self):
        ip = self.cfg["ip"]
        return (f"http://{ip}/cgi-bin/snapManager.cgi"
                f"?action=attachFileProc&Flags[0]=Event&Events={EVENTS}&heartbeat=5")

    def _run_real(self):
        if requests is None:
            print(f"[{self.name}] requests yo'q — ANPR ishlamaydi")
            return
        auth = HTTPDigestAuth(self.cfg.get("login", "admin"), self.cfg.get("password", ""))
        session = requests.Session()
        url = self._url()
        while self._running:
            try:
                print(f"[{self.name}] Ulanmoqda: {url}")
                # read-timeout 30s SHART: kamera har 5s "Heartbeat" yuboradi;
                # 30s jimlik = ulanish o'lgan (half-open socket). Cheksiz (None)
                # bo'lsa tarmoq bir uzilganda listener ABADIY qotadi va qayta
                # ulanmaydi (kuzatildi: 5 kun raqamsiz — kamera esa o'qiyotgan edi).
                resp = session.get(url, auth=auth, stream=True, timeout=(10, 30))
                resp.raise_for_status()
                ctype = resp.headers.get("Content-Type", "")
                m = re.search(r"boundary=([^;]+)", ctype)
                boundary = ("--" + m.group(1).strip()).encode() if m else b"--myboundary"
                buf = b""
                sess_start = time.time()
                for chunk in resp.iter_content(chunk_size=4096):
                    if not self._running:
                        break
                    # PROFILAKTIKA: 6 soatda sessiyani majburan yangilaymiz.
                    # Kuzatildi: Dahua uzoq yashagan sessiyaga heartbeat yuborib
                    # turadi-yu, EVENTlarni yubormay qo'yadi (kamera-side bug) —
                    # read-timeout buni sezmaydi. Yangi sessiya bug'ni tozalaydi.
                    if time.time() - sess_start > 6 * 3600:
                        print(f"[{self.name}] 6h — sessiya profilaktik yangilanadi")
                        break
                    if not chunk:
                        continue
                    buf += chunk
                    while boundary in buf:
                        idx = buf.find(boundary)
                        part, buf = buf[:idx], buf[idx + len(boundary):]
                        self._process_part(part)
                    # himoya: boundary kelmasa bufer cheksiz o'smasin (RAM)
                    if len(buf) > 4 * 1024 * 1024:
                        buf = buf[-1024 * 1024:]
                try:
                    resp.close()
                except Exception:
                    pass
            except Exception as e:
                print(f"[{self.name}] Ulanish xatosi: {e} — 5s dan keyin...")
                time.sleep(5)

    def _process_part(self, part):
        if not part.strip():
            return
        header, _, body = part.partition(b"\r\n\r\n")
        if not body:
            header, _, body = part.partition(b"\n\n")

        # RASM: JPEG (FFD8..FFD9) partning ISTALGAN joyidan (alohida part yoki
        # metama'lumot bilan birga bo'lishi mumkin).
        js = body.find(b"\xff\xd8")
        je = body.rfind(b"\xff\xd9")
        img = body[js:je + 2] if (js != -1 and je > js) else None
        text_body = body[:js] if img is not None else body
        if len(body) > 200:
            self._img_diag(len(body), js, je, header)

        # METAMA'LUMOT — raqam bormi? (binary-xavfsiz dekod)
        plate, group, vtype = None, "", ""
        txt = text_body.decode("latin-1", "ignore")
        if "PlateNumber" in txt or "TrafficCar" in txt or "Events[" in txt:
            self._debug_dump(txt)   # xom formatni faylga (tashxis)
            meta = {}
            for line in txt.splitlines():
                if "=" in line:
                    k, _, v = line.partition("=")
                    meta[k.strip()] = v.strip()
            plate = self._plate_from(meta)
            group = (meta.get("Events[0].TrafficCar.GroupID")
                     or meta.get("Events[0].GroupID") or "")
            # mashina turi — Dahua o'zi klassifikatsiya qiladi (LargeTruck,
            # MicroTruck, Car, Bus, ...). Serverga vtype sifatida yuboriladi.
            vtype = (meta.get("Events[0].TrafficCar.Category")
                     or meta.get("Events[0].Vehicle.Category") or "")

        # MUHIM: Dahua bitta mashina uchun KO'P snapshot (har xil GroupID, bir xil
        # raqam) yuboradi, katta rasm esa raqamdan KEYIN (ba'zan 30-60s) keladi.
        # Raqam DARHOL yuboriladi — rasm kutish YO'Q! (Oldingi 10s kutish vaznni
        # o'tkazib yubordi: vazn raqamdan oldin kelib hodisa raqamsiz ketardi.)
        # Rasm keyin kelganda `_last_emit_images` reference orqali o'z hodisasiga
        # joyida ulanadi (station._watch_late_images + outbox 100s rasm kutadi).
        emit_now = None
        with self._lock:
            now = time.time()
            if plate:
                dup = (self._last_emit_plate == plate and now - self._last_emit_ts < 15)
                if not dup:
                    emit_now = {"plate": plate, "ts": now, "images": [], "vtype": vtype}
                    self._last_emit_plate = plate
                    self._last_emit_ts = now
            if img is not None:
                if (self._last_emit_images is not None
                        and now - self._last_emit_ts < 120):
                    # rasm o'z hodisasiga JOYIDA ulanadi: stansiya buferi/timer/
                    # late-watcher'da AYNI SHU list turadi.
                    li = self._last_emit_images
                    if not li:
                        li.append(img)
                    elif len(img) > len(li[0]):
                        li[0] = img   # kattaroq (to'liq) surat afzal
                    self._img_late_dbg(len(img))

        if emit_now:
            self._emit(emit_now)

    def _emit(self, p):
        """Hodisani yuboradi. Images LISTNING O'ZI beriladi (nusxa emas) —
        kech kelgan rasm keyin shu listga qo'shilishi mumkin. Bir nechta rasm
        bo'lsa joyida eng KATTAsi qoldiriladi (to'liq surat, crop emas)."""
        imgs = p["images"]
        if len(imgs) > 1:
            best = max(imgs, key=len)
            imgs.clear()
            imgs.append(best)
        with self._lock:
            self._last_emit_images = imgs
        self.on_plate(p["plate"], imgs, p["ts"], p.get("vtype"))
        if not imgs and not self.sim and self.active_snapshot:
            # Dahua katta rasmni KECH yoki UMUMAN yubormasligi mumkin (kuzatildi:
            # 90s da ham kelmadi). Kutib o'tirmaymiz — mashina hali kamera
            # oldida turganda joriy kadrni O'ZIMIZ tortib olamiz (snapshot.cgi).
            # Stream'dan haqiqiy ANPR rasmi keyin kelsa, kattarog'i almashadi.
            threading.Thread(target=self._fetch_snapshot, args=(imgs,),
                             name=f"{self.name}-snap", daemon=True).start()

    def _fetch_snapshot(self, imgs):
        """Kameradan joriy kadrni oladi va (hali bo'sh bo'lsa) images listga
        qo'shadi. Zavod ~0.5s, Karyer (sekin link) ~15-18s — late-watcher
        (10/25/55/90s) va outbox rasm-kutishi (100s) bemalol qamraydi."""
        if requests is None:
            return
        try:
            ip = self.cfg.get("ip", "")
            auth = HTTPDigestAuth(self.cfg.get("login", "admin"),
                                  self.cfg.get("password", ""))
            r = requests.get(f"http://{ip}/cgi-bin/snapshot.cgi?channel=1",
                             auth=auth, timeout=(5, 30))
            if r.status_code == 200 and r.content[:2] == b"\xff\xd8":
                with self._lock:
                    if not imgs:
                        imgs.append(r.content)
                self._img_late_dbg(len(r.content))
        except Exception:
            pass   # rasm ixtiyoriy — hodisa baribir ketadi

    def _img_late_dbg(self, size):
        import os
        if os.environ.get("KARYER_ANPR_DEBUG", "1") == "0":
            return
        try:
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img_debug.log")
            if os.path.exists(p) and os.path.getsize(p) > 512 * 1024:
                return
            with open(p, "a", encoding="utf-8") as f:
                f.write(f"[{self.name}] KECH rasm ({size // 1024}KB) -> "
                        f"{self._last_emit_plate} ga qo'shildi\n")
        except Exception:
            pass

    def _plate_from(self, meta):
        """Raqamni meta'dan oladi — firmware'ga bog'liq bo'lmasin: har qanday
        '...PlateNumber' bilan tugaydigan kalit (bo'sh/'unknown' e'tiborsiz).

        VALIDATSIYA: faqat lotin harf/raqamlardan iborat, 5-10 belgili raqam
        qabul qilinadi. Dahua ba'zan chala o'qib "V×¦" kabi axlat beradi —
        bunday hodisa raqamsiz (no_plate) ketgani to'g'ri, operator videodan
        kiritadi; axlat raqam esa qatnov juftlashни ham buzadi."""
        for k, v in meta.items():
            if k.lower().endswith("platenumber") and v:
                cand = v.strip().upper()
                if cand.lower() in ("", "unknown", "none", "null"):
                    continue
                if re.fullmatch(r"[A-Z0-9]{5,10}", cand):
                    return cand
                self._debug_dump(f"AXLAT_RAQAM_RAD_ETILDI={v!r}")
        return None

    def _img_diag(self, blen, js, je, header):
        """Har bir yirik part strukturasi — rasm (JPEG) topilyaptimi (img_debug.log)."""
        import os
        if os.environ.get("KARYER_ANPR_DEBUG", "1") == "0":
            return
        try:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img_debug.log")
            if os.path.exists(path) and os.path.getsize(path) > 512 * 1024:
                return
            hdr = header.decode("latin-1", "ignore").replace("\r", " ").replace("\n", " ").strip()[:80]
            has = "JPEG" if (js != -1 and je > js) else "-"
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"[{self.name}] len={blen} FFD8@{js} FFD9@{je} {has} | hdr='{hdr}'\n")
        except Exception:
            pass

    def _debug_dump(self, txt):
        """ANPR event xom matnini anpr_debug.log ga yozadi (kalit=qiymat).
        Muammoni tashxislash uchun — KARYER_ANPR_DEBUG=0 bilan o'chiriladi."""
        import os
        if os.environ.get("KARYER_ANPR_DEBUG", "1") == "0":
            return
        try:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anpr_debug.log")
            if os.path.exists(path) and os.path.getsize(path) > 1024 * 1024:
                return   # 1MB cheklov — cheksiz o'smasin
            lines = [ln.strip() for ln in txt.splitlines() if "=" in ln]
            if not lines:
                return
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"\n===== [{self.name}] event =====\n")
                f.write("\n".join(lines) + "\n")
        except Exception:
            pass
