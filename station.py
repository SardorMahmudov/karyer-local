#!/usr/bin/env python3
"""
Stansiya orkestratsiyasi.

VideoStation — umumiy mexanizm: ANPR + video kamera + zona detektori.
    Mashina zonaga kirishi bilan video boshlanadi va yo'nalish (in/out)
    videodan aniqlanadi. Hodisa "trigger"i subklassda belgilanadi.

KonStation   — karyer nazorat nuqtasi: zavod bilan BIR XIL tartib, faqat
    tarozi yo'q. Trigger = ANPR raqam: raqam -> zona kesishi (video +
    yo'nalish) -> hodisa -> outbox.
ZavodStation — tarozi + ANPR + video hamohang. Trigger = barqaror vazn:
    tarozi barqaror vazn beradi -> shu vaqtdagi ANPR raqami + video klip
    -> bitta hodisa -> outbox.
"""

import os
import time
import uuid
import threading
import datetime

import db
from config import build_rtsp_url
from anpr_listener import AnprListener
from scale import make_scale_reader, WeightStabilizer
import video_recorder
import media

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TZ_UZ = datetime.timezone(datetime.timedelta(hours=5))


def _now_str():
    return datetime.datetime.now(TZ_UZ).strftime("%Y-%m-%d %H:%M:%S")


def _stamp():
    # millisekund bilan — bir soniyada 2 hodisa fayl nomlari to'qnashmasin
    return datetime.datetime.now(TZ_UZ).strftime("%Y%m%d_%H%M%S_%f")[:-3]


def _link_dbg(msg):
    """Raqam↔vazn bog'lanishini tashxislash (link_debug.log). KARYER_LINK_DEBUG=0 o'chiradi."""
    if os.environ.get("KARYER_LINK_DEBUG", "1") == "0":
        return
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "link_debug.log")
        if os.path.exists(p) and os.path.getsize(p) > 2 * 1024 * 1024:
            return   # 2MB chegara — cheksiz o'smasin
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"{_now_str()} {msg}\n")
    except Exception:
        pass


class BaseStation:
    def __init__(self, station_cfg, quarry_id, save_dir, video_dir, media_cfg=None):
        self.cfg = station_cfg
        self.name = station_cfg["name"]
        self.mode = station_cfg["mode"]
        # serverga yuboriladigan maydonlar
        self.camera_name = station_cfg.get("camera_name") or self.name
        # is_main — serverga yuboriladigan bayroq. Aniq berilsa o'shani olamiz,
        # aks holda eski xatti-harakat: zavod=true, kon=false. Bu tarozisiz
        # (weight_source=none/camera) zavodni ham is_main=true qilib yuborishga imkon beradi.
        is_main = station_cfg.get("is_main")
        self.is_main = (self.mode == "zavod") if is_main is None else bool(is_main)
        self.quarry_id = quarry_id
        self.save_dir = save_dir
        self.video_dir = video_dir
        self.media = media_cfg or {}
        # yengil/yuk chegarasi (kg) — vazndan tur aniqlanadi (config'dan sozlanadi)
        self.LIGHT_MAX_KG = float(station_cfg.get("light_max_kg", 2500))
        # takror-hodisa to'sig'i uchun: [(wall_ts, plate, weight, direction)]
        self._recent_emits = []
        self._emit_lock = threading.Lock()

    # bir xil (raqam, vazn~, YO'NALISH) shu oyna ichida qayta chiqsa — takror
    DEDUP_WINDOW_S = 180
    DEDUP_WEIGHT_TOL = 200   # kg — tarozi tebranishi shu ichida bo'lsa "bir xil"

    def _is_duplicate(self, plate, weight, direction, wall_ts):
        """ALMASHINUV (toggle) modeli: mashinaning OXIRGI hodisasi bilan solishtiradi.

        Yo'nalish oldingidan FARQ qilsa (kirish→chiqish yoki chiqish→kirish) —
        YANGI hodisa. Yo'nalish TAKRORLANSA (kirish→kirish) shu oyna ichida —
        takror (mashina qimirlab/tushib-chiqib qayta chiqargan), o'tkaziladi.
        Shu bilan kirib-chiqib yurgan mashina ham to'g'ri (har almashinuv=hodisa),
        turgan/qimirlagan mashina ham to'sib qolinadi. direction None (yo'nalishsiz,
        Zavod vazn) — oldingidek vazn~ bilan takror aniqlanadi."""
        with self._emit_lock:
            self._recent_emits = [e for e in self._recent_emits
                                  if wall_ts - e[0] <= self.DEDUP_WINDOW_S]
            dup = False
            if plate:
                # shu raqamning OXIRGI hodisasi — yo'nalishi bir xil bo'lsa takror
                last = None
                for e in self._recent_emits:
                    if e[1] == plate:
                        last = e
                if last is not None and last[3] == direction:
                    dup = True
            elif weight is not None:
                # raqamsiz (Zavod vazn): vazn~ + yo'nalish bir xil -> takror
                for _, p, w, d in self._recent_emits:
                    if not p and d == direction and w is not None \
                            and abs(weight - w) <= self.DEDUP_WEIGHT_TOL:
                        dup = True
                        break
            else:
                # raqamsiz, vaznsiz (Karyer YOLO kesish-fallback): oxirgi shu
                # yo'nalishdagi raqamsiz hodisadan DEDUP_WINDOW_S o'tmaguncha takror
                for _, p, w, d in self._recent_emits:
                    if not p and w is None and d == direction:
                        dup = True
                        break
            if not dup:
                self._recent_emits.append((wall_ts, plate, weight, direction))
            return dup

    def _save_images(self, images, prefix):
        """Rasmlarni SIQIB saqlaydi (yuborishdan oldin hajm kichrayadi)."""
        paths = []
        if not images:
            return paths
        os.makedirs(self.save_dir, exist_ok=True)
        q = self.media.get("image_quality", 70)
        mw = self.media.get("image_max_width", 1280)
        for i, img in enumerate(images):
            p = os.path.join(self.save_dir, f"{prefix}_{i}.jpg")
            try:
                data = media.compress_image_bytes(img, quality=q, max_width=mw)
                with open(p, "wb") as f:
                    f.write(data)
                paths.append(p)
            except Exception as e:
                print(f"[{self.name}] rasm saqlashda xato: {e}")
        return paths

    def _record_event(self, plate, weight, image_paths=None, video_path=None,
                      direction=None, vtype=None):
        """Hodisani lokal bazaga yozadi va DARHOL outbox navbatiga qo'yadi.
        (event_id, payload) qaytaradi. Video hali yozilayotgan bo'lsa outbox
        faylni kutadi (.part tayyor bo'lgach paydo bo'ladi).

        direction: video (zonaga kirish) aniqlagan yo'nalish. None bo'lsa —
        raqam-almashinuv (toggle) fallback ishlatiladi."""
        event_time = _now_str()

        # TUR — VAZN USTUVOR: Dahua kamera yengil/yuk mashinani ishonchli
        # ajrata olmaydi (yengilni ham "yuk" deydi). Tarozi bor bo'lsa (zavod)
        # TURNI VAZN belgilaydi — kamera Category'sini e'tiborsiz qoldiramiz:
        #   < LIGHT_MAX_KG (2.5t) -> Car (yengil), aks holda -> LargeTruck (yuk).
        # Tarozi yo'q joyда (Karyer, weight=None) — kamera turi qoladi.
        if weight is not None:
            vtype = "Car" if weight < self.LIGHT_MAX_KG else "LargeTruck"

        # VAZN-YO'NALISH (bir yo'lakli tarozi — video yo'nalish ishonchsiz,
        # mashina chiqishда ham kirish yo'lagidan tarozига keladi). Config
        # "direction_from_weight": true bo'lsa yo'nalishni VAZN belgilaydi:
        # birinchi=kirish, keyingisi >= threshold og'ir=chiqish, aks holda kirish.
        # Faqat raqam+vazn bor bo'lganda (juftlash raqam bo'yicha).
        if plate and weight is not None and self.cfg.get("direction_from_weight"):
            thr = self.cfg.get("direction_weight_threshold_kg", 5000)
            rh = self.cfg.get("direction_reset_hours", 24)
            direction = db.trip_direction(self.name, plate, weight,
                                          threshold_kg=thr, reset_hours=rh)

        if direction is not None:
            # holat jadvalini moslab qo'yamiz (vazn-yo'nalish o'zi yozadi, lekin
            # video-yo'nalish kelsa ham izchil bo'lsin)
            if plate and not (self.cfg.get("direction_from_weight") and weight is not None):
                db.set_direction_state(self.name, plate, direction)
        elif plate and self.cfg.get("direction_toggle", False):
            # ZAXIRA (default O'CHIQ): zona kesmasa raqam-almashinuv bilan in/out.
            # O'chiq bo'lsa yo'nalish None qoladi — noto'g'ri "toggle" bermaymiz
            # (config'da "direction_toggle": true bilan yoqiladi).
            reset_h = self.cfg.get("direction_reset_hours", 12)
            direction = db.toggle_direction(self.name, plate, reset_hours=reset_h)

        # lokal baza yozuvi (tashxis uchun station/mode saqlanadi)
        ev = {
            "quarry_id": self.quarry_id,
            "station": self.name,
            "mode": self.mode,
            "plate": plate,
            "direction": direction,
            "weight": weight,
            "unit": "kg",
            "event_time": event_time,
            "video_path": video_path,
            "image_paths": image_paths or [],
        }
        # serverga yuboriladigan payload (camera_name + is_main + direction)
        # event_uid — idempotency kaliti: qayta yuborishda server dublikatni ajratadi
        # Eslatma: "no_plate"/holatni server O'ZI hisoblaydi (plate bo'shligidan) —
        # local faqat xom faktni yuboradi (plate=None bo'lishi mumkin).
        payload = {
            "event_uid": str(uuid.uuid4()),
            "quarry_id": self.quarry_id,
            "camera_name": self.camera_name,
            "is_main": self.is_main,
            "plate": plate,
            "direction": direction,
            "weight": weight,
            "unit": "kg",
            "event_time": event_time,
            "video_path": video_path,
            "image_paths": image_paths or [],
            "vtype": vtype or "",   # Dahua mashina turi (LargeTruck/Car/...)
        }
        event_id = db.insert_event(ev)
        # fallback-dedup uchun: stansiyada oxirgi hodisa qachon yozilgani
        self._last_event_wall = time.time()
        # DARHOL navbatga — video hali yozilayotgan bo'lsa ham (fayl .part'da,
        # out_path faqat TO'LIQ bo'lganda paydo bo'ladi; outbox o'zi kutadi).
        # Shu bilan restart/crash paytida hodisa YO'QOLMAYDI.
        db.enqueue_outbox(event_id, payload)
        wtxt = f"{weight} kg" if weight is not None else "-"
        dtxt = {"in": "KIRISH ⬅", "out": "CHIQISH ➡"}.get(direction, "?")
        print(f"\n📦 [{self.name}] HODISA #{event_id}: raqam={plate} | {dtxt} | vazn={wtxt} | {event_time}")
        print("    -> outbox navbatiga qo'yildi (serverga yuboriladi)\n")
        return event_id, payload

    def _watch_late_images(self, event_id, payload, images_ref, prefix):
        """Dahua katta rasmni (0.6-1.4MB) ba'zan raqamdan 30-60s KEYIN yuboradi.
        Hodisa rasmsiz yozilgan bo'lsa — anpr_listener kech kelgan rasmni
        images_ref listiga JOYIDA qo'shadi; biz 30/60/90s da tekshirib, rasm
        kelgach payload'ni yangilaymiz. Outbox esa rasmni ~100s kutib turadi
        (api_client), shuning uchun hodisa serverga RASM BILAN yetadi;
        kelmasa — rasmsiz ketadi, hech narsa yo'qolmaydi."""
        if not payload.get("plate") or payload.get("image_paths") or images_ref is None:
            return

        delays = [10.0, 15.0, 30.0, 35.0]   # jami 10/25/55/90s da tekshiradi

        def _try(attempt):
            if not images_ref:
                if attempt < len(delays):
                    threading.Timer(delays[attempt], _try, args=(attempt + 1,)).start()
                else:
                    _link_dbg(f"  late-img: #{event_id} rasm 90s da ham kelmadi — rasmsiz ketadi")
                return
            paths = self._save_images(images_ref, prefix + "_late")
            if paths:
                payload["image_paths"] = paths
                db.update_outbox_payload(event_id, payload)
                db.set_event_images(event_id, paths)
                _link_dbg(f"  late-img: #{event_id} rasm KECHIKIB keldi -> qo'shildi")

        threading.Timer(delays[0], _try, args=(1,)).start()


class VideoStation(BaseStation):
    """ANPR + video kamera + zona detektori — umumiy mexanizm (tarozisiz).

    Zona chizilgan bo'lsa: mashina zonaga kirishi bilan video DARHOL boshlanadi
    va yo'nalish (in/out) videodan aniqlanadi. Zona bo'lmasa: hodisa paytida
    video yoziladi, yo'nalish raqam-almashinuv (toggle) fallback bilan.
    Hodisa trigger'i subklassda: KON — ANPR raqam, ZAVOD — barqaror vazn.
    """

    def __init__(self, station_cfg, quarry_id, save_dir, video_dir, sim=False, media_cfg=None):
        super().__init__(station_cfg, quarry_id, save_dir, video_dir, media_cfg)
        self.sim = sim
        self._lock = threading.Lock()

        # video kamera (main stream) — video KLIP shu oqimdan yoziladi (yuqori sifat)
        vcfg = station_cfg.get("video", {})
        self.rtsp = vcfg.get("rtsp_main") or (
            build_rtsp_url(vcfg.get("brand", "dahua"), vcfg.get("ip", ""),
                           vcfg.get("login", "admin"), vcfg.get("password", ""))
            if vcfg.get("ip") else None
        )
        # SUB oqim — YOLO detektori uchun. Kamera bir vaqtda cheklangan oqim
        # beradi; detektor main'ni doimo ushlab tursa, video yozishga oqim
        # qolmaydi. Shuning uchun detektor SUB'da (yengil), yozish MAIN'da.
        self.rtsp_sub = (
            build_rtsp_url(vcfg.get("brand", "dahua"), vcfg.get("ip", ""),
                           vcfg.get("login", "admin"), vcfg.get("password", ""),
                           subtype=1)
            if vcfg.get("ip") else None
        )
        # YOZISH oqimi: default MAIN (sifatli). Kamera uzoq/sekin tarmoq ortida
        # bo'lsa (masalan karyer radiolinki) MAIN 1440p HEVC harakat paytida
        # linkni to'ydirib, video uzuq chiqadi — "record_substream": true bilan
        # yengil SUB oqimdan yoziladi (past sifat, lekin BUTUN video).
        self.rtsp_rec = self.rtsp
        if vcfg.get("record_substream") and self.rtsp_sub:
            self.rtsp_rec = self.rtsp_sub
        self.capture = station_cfg.get("capture", {"duration": 10, "delay": 0})

        # zona detektori: mashina zonaga kirishi bilan video boshlanadi
        # va yo'nalish (in/out) aniqlanadi
        self.crossing_window = station_cfg.get("crossing_window", 40.0)
        self._crossings = []   # [{ts, direction, video_path, done, result_path, pending}]
        self._last_rec_ts = 0.0   # oxirgi video yozish boshlangan vaqt (overlap oldini olish)
        self.detector = None
        zone = station_cfg.get("zone")
        det_cfg = station_cfg.get("detector", {})
        if (self.rtsp and zone and zone.get("polygon")
                and det_cfg.get("enabled", True) and not sim):
            from detector import VideoZoneDetector
            # detektor SUB oqimda (config'da substream=false bo'lsa main'da)
            det_rtsp = self.rtsp
            if det_cfg.get("substream", True) and self.rtsp_sub:
                det_rtsp = self.rtsp_sub
            self.detector = VideoZoneDetector(
                det_rtsp, zone, self._on_zone_enter,
                det_cfg=det_cfg, name=f"{self.name}-det")

    def start(self):
        if self.detector:
            self.detector.start()

    def stop(self):
        if self.detector:
            self.detector.stop()

    # ---- zonaga kirildi: DARHOL video boshlanadi, yo'nalish yozib olinadi ----
    def _on_zone_enter(self, direction, ts, vclass=""):
        # OVERLAP oldini olish: bir mashina zonani bir necha marta kesadi. Oxirgi
        # yozish hali tugamagan bo'lsa (klip uzunligi ichida), yangi yozish
        # boshlamaymiz — bir vaqtda 2 yozish kamera MAIN oqimini talashib videoni
        # buzadi (uzuq/qotgan kadr). Birinchi yozuv mashinani qamrab oladi.
        now = time.time()
        with self._lock:
            skip = self.rtsp and (now - self._last_rec_ts) < self.capture.get("duration", 10)
            if not skip:
                self._last_rec_ts = now
        if skip:
            # video YOZILMAYDI (oldingi yozuv hali ketmoqda — oqim talashmasin),
            # lekin kesish YO'NALISH uchun baribir ro'yxatga olinadi.
            _link_dbg(f"ZONE kesish videosiz (overlap) dir={direction} ts={ts:.1f}")
            crossing = {"ts": ts, "direction": direction, "video_path": None,
                        "done": True, "result_path": None, "pending": None,
                        "vclass": vclass}
            with self._lock:
                self._crossings.append(crossing)
            return
        dtxt = "KIRISH ⬅" if direction == "in" else "CHIQISH ➡"
        print(f"[{self.name}] 🚧 Zonaga kirdi: {dtxt} — video boshlanmoqda...")
        _link_dbg(f"ZONE kesish dir={direction} ts={ts:.1f} tur={vclass}")
        crossing = {"ts": ts, "direction": direction, "video_path": None,
                    "done": False, "result_path": None, "pending": None,
                    "vclass": vclass}

        if self.rtsp:
            video_path = os.path.join(
                self.video_dir, f"{self.name}_{direction}_{_stamp()}.mp4")
            crossing["video_path"] = video_path

            def _done(path):
                to_fix = None
                with self._lock:
                    crossing["done"] = True
                    crossing["result_path"] = path
                    if crossing["pending"] is not None:
                        to_fix = crossing["pending"]
                        crossing["pending"] = None
                if path:
                    print(f"[{self.name}] video tayyor: {path}")
                else:
                    print(f"[{self.name}] ⚠️ video yozilmadi")
                # hodisa allaqachon navbatda (video yo'lini kutyapti); yozish
                # MUVAFFAQIYATSIZ bo'lsa — payload'dan videoni olib tashlaymiz,
                # aks holda outbox mavjud bo'lmaydigan faylni kutib qoladi.
                if to_fix and not path:
                    event_id, payload = to_fix
                    payload["video_path"] = None
                    db.update_outbox_payload(event_id, payload)

            # PRE-ROLL: detektor kadrlarni bufferlab turadi — kesishDAN OLDINGI
            # soniyalar ham videoga tushadi (mashina o'tib ketgandan keyin emas).
            # Buferда yetarli kadr bo'lmasa (masalan endi ishga tushган) yoki
            # xato bo'lsa — eski usul (RTSP'дан yozib) zaxira sifatida ishlaydi.
            if self.detector and self.cfg.get("video", {}).get("preroll_clip", True):
                self.detector.write_clip(video_path, ts, on_done=_done,
                                         media_cfg=self.media)
            else:
                video_recorder.record_clip_async(
                    self.rtsp_rec, video_path,
                    duration=self.capture.get("duration", 10),
                    delay=self.capture.get("delay", 0),
                    on_done=_done,
                    media_cfg=self.media,
                )
        else:
            crossing["done"] = True

        with self._lock:
            self._crossings.append(crossing)
            cutoff = ts - max(self.crossing_window * 3, 120)
            self._crossings = [c for c in self._crossings if c["ts"] >= cutoff]

    def _pick_crossing(self, event_ts):
        """Hodisa vaqtiga mos zona-kirishini oladi va buferdan olib tashlaydi.

        Mashina avval zonaga kiradi, KEYIN hodisa yuz beradi — shuning uchun
        o'tmishdagi (ts <= event_ts) ENG SO'NGGI kesish ustuvor.
        Bo'lmasa (juda kam holat) — kelajakdagi eng yaqini.
        Aks holda keyingi mashinaning kesishi adashib olinishi mumkin."""
        with self._lock:
            cands = [c for c in self._crossings
                     if abs(c["ts"] - event_ts) <= self.crossing_window]
            if not cands:
                return None
            past = [c for c in cands if c["ts"] <= event_ts]
            if past:
                chosen = max(past, key=lambda c: c["ts"])       # eng so'nggi o'tmish
                if not chosen["video_path"]:
                    # tanlangani videosiz (overlap) — o'sha klip oynasi ichida
                    # VIDEOLI sherigi bo'lsa (ayni shu mashinaning asl kesishi),
                    # o'shani olamiz.
                    dur = self.capture.get("duration", 10)
                    with_video = [c for c in past
                                  if c["video_path"] and chosen["ts"] - c["ts"] <= dur]
                    if with_video:
                        chosen = max(with_video, key=lambda c: c["ts"])
            else:
                chosen = min(cands, key=lambda c: c["ts"])      # eng yaqin kelajak
            self._crossings.remove(chosen)
            return chosen

    def _has_crossing(self, event_ts):
        """Hodisa vaqtiga mos kesish bormi — buferdan OLMASDAN tekshiradi."""
        with self._lock:
            return any(abs(c["ts"] - event_ts) <= self.crossing_window
                       for c in self._crossings)

    def _lookup_plate(self, event_ts):
        """Hodisa vaqtiga mos ANPR raqamni qaytaradi (plate, images, vtype).
        Faqat raqamni buferlab ishlaydigan stansiya (zavod) override qiladi."""
        return None, [], None

    def _finalize_event(self, event_ts, weight, plate=None, images=None, vtype=None,
                        waited_zone=False, waited_plate=False):
        """Hodisani yakunlaydi: rasmlarni saqlaydi, bazaga DARHOL yozadi.

        Ustuvorlik:
          1) Zona kirishi topilsa — yo'nalish va video O'SHANDAN olinadi
             (video mashina zonaga kelganda ALLAQACHON boshlangan).
          2) Topilmasa — eski usul: video hozir yoziladi, yo'nalish raqam
             almashinuvidan (fallback).
        """
        if plate is None:
            lk_plate, lk_images, lk_vtype = self._lookup_plate(event_ts)
            plate, images = lk_plate, lk_images
            # lookup vtype faqat raqam topilганда ustuvor; topilmasa chaqiruvda
            # kelgan vtype (masalan YOLO-klass, kesish-fallback) saqlanadi.
            if lk_plate is not None:
                vtype = lk_vtype
            # RAQAM-KUTISH (faqat raqam-buferli stansiya — zavod): ANPR raqamni
            # vazndan 10-15s KEYIN ham o'qishi mumkin (tez o'tgan yengil mashina:
            # vazn 08:40:30, raqam 08:40:44 — hodisa raqamsiz/tursiz ketdi).
            # Topilmasa BIR marta 15s kutib qayta urinamiz.
            if (plate is None and not waited_plate
                    and getattr(self, "_recent_plates", None) is not None):
                _link_dbg("  finalize: raqam hali yo'q — 15s kutilyapti...")
                threading.Timer(15.0, self._finalize_event,
                                args=(event_ts, weight, None, None, None,
                                      waited_zone, True)).start()
                return

        # Zona kesishi hali kelmagan bo'lsa — bir marta kutamiz (YOLO kechikadi).
        # waited_zone: cheksiz qayta-kutish bo'lmasligi uchun bayroq.
        if (not waited_zone and self.detector and plate is not None
                and not self._has_crossing(event_ts)):
            grace = min(self.crossing_window, 12.0)
            _link_dbg(f"  finalize: zona yo'q — {grace:.0f}s kutilyapti...")
            threading.Timer(grace, self._finalize_event,
                            args=(event_ts, weight, plate, images, vtype, True)).start()
            return

        # RASM bo'sh bo'lsa — detektor BUFFERIDAN o'sha paytdagi kadrni olamiz.
        # Aktiv snapshot (kamera sekin, ~15s) mashina ketgach BO'SH YO'L beradi
        # (ayniqsa ketma-ket 2 mashinada — kuzatildi: 2-mashina rasmi bo'sh).
        # Buffer kadri esa AYNAN o'sha vaqtdagi mashinani ko'rsatadi (videoli).
        if not images and self.detector is not None:
            jpg = self.detector.grab_frame(event_ts)
            if jpg:
                images = [jpg]
                _link_dbg(f"  rasm: detektor bufferidan olindi ({len(jpg)//1024}KB)")

        # Yo'nalishni kesishdan olamiz (dedup uchun — kirish≠chiqish alohida).
        crossing = self._pick_crossing(event_ts)
        direction = crossing["direction"] if crossing else None

        # TAKROR-HODISA to'sig'i: AYNI mashina AYNI YO'NALISHDA qisqa vaqtda
        # qayta chiqsa (tarozida qimirlash / tushib-chiqish) — o'tkaziladi.
        # Kirib-chiqish (har xil yo'nalish) esa IKKI alohida hodisa — o'tmaydi.
        if self._is_duplicate(plate, weight, direction, time.time()):
            _link_dbg(f"  TAKROR o'tkazildi: raqam={plate} vazn={weight} yo'n={direction}")
            return

        prefix = f"{self.name}_{plate or 'NOPLATE'}_{_stamp()}"
        image_paths = self._save_images(images, prefix)

        if crossing is not None:
            # video zonaga kirilganda boshlangan; yo'nalish videodan.
            # Hodisa DARHOL navbatga tushadi (_record_event ichida) — video
            # tayyor bo'lgach fayl paydo bo'ladi, outbox o'zi kutib yuboradi.
            with self._lock:
                vp = crossing["result_path"] if crossing["done"] else crossing["video_path"]
            event_id, payload = self._record_event(
                plate, weight, image_paths=image_paths,
                video_path=vp, direction=crossing["direction"], vtype=vtype)
            with self._lock:
                if not crossing["done"]:
                    # yozish muvaffaqiyatsiz tugasa _done payload'ni tuzatadi
                    crossing["pending"] = (event_id, payload)
            self._watch_late_images(event_id, payload, images, prefix)
            return

        if self.rtsp:
            # fallback: zona kirishi aniqlanmadi — videoni hozir yozamiz
            video_path = os.path.join(self.video_dir, f"{prefix}.mp4")
            event_id, payload = self._record_event(
                plate, weight, image_paths=image_paths, video_path=video_path, vtype=vtype)

            def _done(path):
                if path:
                    print(f"[{self.name}] video tayyor: {path}")
                else:
                    print(f"[{self.name}] ⚠️ video yozilmadi — videosiz yuboriladi")
                    payload["video_path"] = None
                    db.update_outbox_payload(event_id, payload)

            video_recorder.record_clip_async(
                self.rtsp_rec, video_path,
                duration=self.capture.get("duration", 10),
                delay=self.capture.get("delay", 0),
                on_done=_done,
                media_cfg=self.media,
            )
            self._watch_late_images(event_id, payload, images, prefix)
        else:
            # video yo'q — hodisa darhol yozildi va navbatга tushdi
            event_id, payload = self._record_event(
                plate, weight, image_paths=image_paths,
                video_path=None, vtype=vtype)
            self._watch_late_images(event_id, payload, images, prefix)


class KonStation(VideoStation):
    """Karyer nazorat nuqtasi: ANPR + video — zavod bilan bir xil tartib,
    faqat tarozi yo'q (weight doim None).

    ANPR raqam hodisani boshlaydi; video va yo'nalish zona kesishidan olinadi.
    Video kamera sozlanmagan bo'lsa — eski usul: faqat raqam + rasm."""

    def __init__(self, station_cfg, quarry_id, save_dir, video_dir, sim=False, media_cfg=None):
        super().__init__(station_cfg, quarry_id, save_dir, video_dir,
                         sim=sim, media_cfg=media_cfg)
        self.anpr = AnprListener(station_cfg["anpr"], self._on_plate,
                                 name=self.name, sim=sim)
        # raqam va zona kesishi deyarli bir vaqtda keladi — detektor biroz
        # kechiksa hodisani shu muddatga kutib turamiz
        self.crossing_grace = min(self.crossing_window, 5.0)
        # kesish-fallback dedup: bir o'tish = bitta hodisa
        self._last_fb_event_ts = 0.0

    def _on_zone_enter(self, direction, ts, vclass=""):
        super()._on_zone_enter(direction, ts, vclass)
        # RAQAMSIZ FALLBACK: CHIQISHDA ANPR mashinaning ORQASINI ko'radi —
        # raqam o'qilmaydi, hodisa yaratilmasdi va yozilgan video hech qayerga
        # ulanmay qolardi (kuzatildi: 433 kesish, 4 hodisa, chiqishlar 0).
        # Kesishdan 45s ichida raqamli hodisa bu kesishni olmasa — kesishning
        # o'zi hodisa bo'ladi: video + yo'nalish, raqam yo'q (server "Chalkashlik",
        # operator videodan kiritadi).
        threading.Timer(45.0, self._crossing_fallback, args=(ts,)).start()

    def _crossing_fallback(self, ts):
        with self._lock:
            c = next((c for c in self._crossings if c["ts"] == ts), None)
        if c is None or not c.get("video_path"):
            return   # raqamli hodisa ishlatgan yoki videosiz overlap-kesish
        now = time.time()
        # bir mashina o'tishi ~30-60s da 2-3 kesish beradi — stansiyada
        # (raqamli yoki raqamsiz) OXIRGI hodisadan 120s o'tmaguncha yangi
        # fallback ochmaymiz (kuzatildi: 25H974LA dan keyin 2 ta ortiqcha
        # raqamsiz hodisa ketgan edi).
        if now - getattr(self, "_last_event_wall", 0) < 120:
            return
        if now - self._last_fb_event_ts < 120:
            return
        self._last_fb_event_ts = now
        # tur — YOLO detektori aniqlagan mashina klassidan (Karyer'da tarozi
        # yo'q; raqam ham o'qilmagan, aks holda bu fallback ishlamasdi).
        vtype = c.get("vclass") or ""
        _link_dbg(f"KESISH-FALLBACK: raqam kelmadi, kesish o'zi hodisa bo'ladi "
                  f"(dir={c['direction']} ts={ts:.1f} tur={vtype})")
        self._finalize_event(ts, None, vtype=vtype)

    def start(self):
        extra = " + video" if self.rtsp else ""
        print(f"▶ KON stansiyasi ishga tushdi: {self.name} (ANPR{extra})")
        self.anpr.start()
        super().start()

    def stop(self):
        self.anpr.stop()
        super().stop()

    def _on_plate(self, plate, images, ts, vtype=None):
        print(f"[{self.name}] ANPR raqam: {plate}")
        if self.detector and not self._has_crossing(ts):
            # zona detektori kesishni raqamdan kechroq berishi mumkin —
            # video va yo'nalish yo'qolmasligi uchun biroz kutamiz
            print(f"[{self.name}] zona kesishi hali yo'q — {self.crossing_grace:.0f}s kutilmoqda...")
            threading.Timer(self.crossing_grace, self._finalize_event,
                            args=(ts, None, plate, images, vtype)).start()
            return
        self._finalize_event(ts, None, plate, images, vtype)


class ZavodStation(VideoStation):
    """Tarozi + ANPR + video hamohang stansiyasi (asosiy)."""

    def __init__(self, station_cfg, quarry_id, save_dir, video_dir, sim=False, media_cfg=None):
        super().__init__(station_cfg, quarry_id, save_dir, video_dir,
                         sim=sim, media_cfg=media_cfg)
        self.anpr_window = station_cfg.get("anpr_window", 8.0)
        self._recent_plates = []   # [(ts, plate, images, vtype)]

        # tarozi
        scfg = dict(station_cfg["scale"])
        if sim:
            scfg["type"] = "sim"
        self.scale = make_scale_reader(scfg)
        self.stab = WeightStabilizer(
            min_weight=scfg.get("min_weight", 500),
            settle_time=scfg.get("settle_time", 3.0),
            stability_tolerance=scfg.get("stability_tolerance", 20),
            division=scfg.get("division", 10),
            tie_break=scfg.get("tie_break", "largest"),
            min_samples=scfg.get("min_samples", 5),
        )

        # ANPR
        self.anpr = AnprListener(station_cfg["anpr"], self._on_plate,
                                 name=f"{self.name}-anpr", sim=sim)

    def start(self):
        print(f"▶ ZAVOD stansiyasi ishga tushdi: {self.name}")
        self.anpr.start()
        self.scale.start(self._on_weight)
        super().start()

    def stop(self):
        self.anpr.stop()
        self.scale.stop()
        super().stop()

    # ANPR raqamlarini vaqt bilan buferga yig'amiz
    def _on_plate(self, plate, images, ts, vtype=None):
        with self._lock:
            self._recent_plates.append((ts, plate, images, vtype))
            # eski yozuvlarni tozalaymiz
            cutoff = ts - max(self.anpr_window * 3, 30)
            self._recent_plates = [r for r in self._recent_plates if r[0] >= cutoff]
        print(f"[{self.name}] ANPR raqam: {plate} ({vtype or '-'})")
        _link_dbg(f"PLATE buferga: {plate} ts={ts:.1f} rasm={len(images)} tur={vtype}")

    def _pick_plate(self, weigh_ts):
        """Tortish vaqtiga eng yaqin (anpr_window ichidagi) raqamni oladi
        va uni buferdan olib tashlaydi (keyingi mashinaga yopishmasin)."""
        with self._lock:
            cands = [r for r in self._recent_plates
                     if abs(r[0] - weigh_ts) <= self.anpr_window]
            if not cands:
                return None, [], None
            # eng yaqin vaqtdagisi
            cands.sort(key=lambda r: abs(r[0] - weigh_ts))
            chosen = cands[0]
            self._recent_plates.remove(chosen)
            _, plate, images, vtype = chosen
            return plate, images, vtype

    def _lookup_plate(self, event_ts):
        return self._pick_plate(event_ts)

    # tarozi har o'qishda chaqiradi
    def _on_weight(self, reading):
        weight = self.stab.feed(reading.weight, reading.ts)
        if weight is None:
            return
        # barqaror vazn tayyor — hodisa yaratamiz
        print(f"[{self.name}] ⚖️ Barqaror vazn: {weight} kg")
        weigh_ts = reading.ts
        with self._lock:
            buf = [(round(weigh_ts - t, 1), p) for t, p, _, _ in self._recent_plates]
        _link_dbg(f"WEIGHT {weight}kg weigh_ts={weigh_ts:.1f} oyna={self.anpr_window}s "
                  f"bufer(farq_s,raqam)={buf}")
        plate, images, vtype = self._pick_plate(weigh_ts)
        _link_dbg(f"  -> tanlandi: {plate} ({vtype})")

        if plate is None:
            # ANPR biroz kechikishi mumkin — raqamni kutib olamiz (bloklamasdan)
            grace = min(self.anpr_window, 5.0)
            print(f"[{self.name}] raqam hali yo'q — {grace:.0f}s kutilmoqda...")
            threading.Timer(grace, self._finalize_event, args=(weigh_ts, weight)).start()
            return

        # zona kesishi kechiksa _finalize_event o'zi kutadi (waited_zone bayrog'i)
        self._finalize_event(weigh_ts, weight, plate, images, vtype)


def make_station(station_cfg, quarry_id, save_dir, video_dir, sim=False, media_cfg=None):
    """Stansiya turini VAZN MANBAI bo'yicha tanlaydi (rejim/is_main dan mustaqil):

      - weight_source="scale" (yoki sim) -> ZavodStation: barqaror vazn hodisani
        boshlaydi (KELI D12 serial tarozi).
      - aks holda ("none" / "camera") -> KonStation mexanizmi: hodisani ANPR
        raqam boshlaydi, video + yo'nalish zonadan/olinadi, weight=null.
        is_main config'dan olinadi — shu bilan tarozisiz zavodni ham
        is_main=true qilib yuborsa bo'ladi (2-usul: vazn keyin kamera OCR bilan).

    Eski configlarda weight_source bo'lmasa: zavod->scale, kon->none (mos-kelish)."""
    ws = station_cfg.get("weight_source")
    if ws is None:
        ws = "scale" if station_cfg.get("mode") == "zavod" else "none"
    if ws == "scale":
        return ZavodStation(station_cfg, quarry_id, save_dir, video_dir,
                            sim=sim, media_cfg=media_cfg)
    return KonStation(station_cfg, quarry_id, save_dir, video_dir,
                     sim=sim, media_cfg=media_cfg)
