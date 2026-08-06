#!/usr/bin/env python3
"""
Video ZONA detektori (yo'nalish + video trigger).

Video kamerada chizilgan ZONA (polygon) va uning ikki tomoni belgilanadi:
  - KIRISH tomoni (entry_edge)  — bu tomondan kirgan mashina "in"
  - CHIQISH tomoni (exit_edge)  — bu tomondan kirgan mashina "out"

Mashina zonaga kirishi bilanoq:
  - qaysi tomondan kirgani aniqlanadi -> yo'nalish (in/out)
  - callback chaqiriladi -> stansiya darhol video yozishni boshlaydi

Ikki qism:
  ZoneDirectionTracker — sof matematika (YOLOsiz), testlanadi
  VideoZoneDetector    — RTSP + YOLO (ultralytics) -> tracker -> callback

Zona formati (config, normalized 0-1):
  {"polygon": [[x,y],...],
   "entry_edge": [[x,y],[x,y]],   # KIRISH tomoni (ikki nuqta)
   "exit_edge":  [[x,y],[x,y]]}   # CHIQISH tomoni
"""

import os
import time
import threading
import subprocess
from collections import deque


# =========================================================
#  Geometriya yordamchilari
# =========================================================
def point_in_poly(x, y, poly):
    """Ray-casting: nuqta polygon ichidami."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and \
                (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def dist_to_segment(px, py, a, b):
    """Nuqtadan kesma (a-b) gacha eng qisqa masofa."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


# =========================================================
#  SOF MANTIQ — zona kirishini va yo'nalishni kuzatish
# =========================================================
class ZoneDirectionTracker:
    """Mashina zonaga KIRGANDA yo'nalishni aniqlaydi: kirish nuqtasi
    KIRISH tomoniga yaqinmi -> 'in', CHIQISH tomoniga yaqinmi -> 'out'."""

    def __init__(self, zone, match_dist=0.15, track_ttl=4.0, cooldown=5.0,
                 edge_near=0.12, stay_quiet=20.0):
        self.poly = [tuple(p) for p in zone["polygon"]]
        ee = zone["entry_edge"]
        xe = zone["exit_edge"]
        self.entry_seg = (tuple(ee[0]), tuple(ee[1]))
        self.exit_seg = (tuple(xe[0]), tuple(xe[1]))
        self.match_dist = match_dist
        self.track_ttl = track_ttl
        self.cooldown = cooldown
        # YOLO mashinani KECH aniqlasa (allaqachon zona ichida), lekin chekkaga
        # shu masofadan yaqin bo'lsa — o'sha chekkadan kirgan deb hisoblaymiz.
        self.edge_near = edge_near
        # TAROZIDA TURGAN mashina himoyasi: YOLO trackni bir zum yo'qotib qayta
        # topsa, yangi track "zonada paydo bo'ldi" bo'lib YOLG'ON kesish beradi
        # (kuzatildi: in dan 13s keyin yolg'on out -> hodisa "Chiqish" bo'lib
        # ketdi). Oxirgi kesishdan keyin shu oynada zonada PAYDO bo'lgan track
        # yangi kesish hisoblanmaydi (haqiqiy tashqaridan->ichkariga o'tishlar
        # bunga tegmaydi — ketma-ket mashinalar buzilmaydi).
        self.stay_quiet = stay_quiet
        self._last_event_ts = None
        self._tracks = []   # [{cx, cy, inside, ts, counted_at}]

    def update(self, centers, ts):
        """centers: [(cx,cy)] normalized. Qaytaradi: [("in"|"out", ts)]."""
        events = []
        self._tracks = [t for t in self._tracks if ts - t["ts"] <= self.track_ttl]

        used = set()
        for cx, cy in centers:
            inside = point_in_poly(cx, cy, self.poly)

            best, best_d = None, self.match_dist
            for i, tr in enumerate(self._tracks):
                if i in used:
                    continue
                d = ((tr["cx"] - cx) ** 2 + (tr["cy"] - cy) ** 2) ** 0.5
                if d < best_d:
                    best, best_d = i, d

            if best is None:
                # yangi track. Zona ICHIDA paydo bo'lsa (YOLO kech aniqladi):
                # chekkalardan biriga yetarli yaqin bo'lsa — o'sha tomondan
                # KIRGAN deb hisoblaymiz (aks holda, o'rtada paydo bo'lsa —
                # qaysi tomondan kirgani noma'lum, hodisa chiqarmaymiz).
                counted = None
                if inside:
                    counted = ts
                    quiet = (self._last_event_ts is not None
                             and ts - self._last_event_ts < self.stay_quiet)
                    d_entry = dist_to_segment(cx, cy, *self.entry_seg)
                    d_exit = dist_to_segment(cx, cy, *self.exit_seg)
                    if not quiet and min(d_entry, d_exit) <= self.edge_near:
                        direction = "in" if d_entry <= d_exit else "out"
                        events.append((direction, ts))
                        self._last_event_ts = ts
                self._tracks.append({"cx": cx, "cy": cy, "inside": inside,
                                     "ts": ts, "counted_at": counted})
                continue

            used.add(best)
            tr = self._tracks[best]
            was_inside = tr["inside"]

            # tashqaridan -> ichkariga o'tdi = zonaga KIRDI
            if inside and not was_inside:
                if tr["counted_at"] is None or ts - tr["counted_at"] >= self.cooldown:
                    d_entry = dist_to_segment(cx, cy, *self.entry_seg)
                    d_exit = dist_to_segment(cx, cy, *self.exit_seg)
                    direction = "in" if d_entry <= d_exit else "out"
                    events.append((direction, ts))
                    tr["counted_at"] = ts
                    self._last_event_ts = ts
            tr.update(cx=cx, cy=cy, inside=inside, ts=ts)

        return events


# =========================================================
#  RTSP + YOLO detektor
# =========================================================
# COCO klasslari: 2=car, 5=bus, 7=truck
VEHICLE_CLASSES = [2, 5, 7]
# COCO -> bizning tur (server: "car"=yengil, boshqasi=yuk)
_COCO_VTYPE = {2: "Car", 5: "Bus", 7: "LargeTruck"}


class VideoZoneDetector:
    """RTSP oqimini YOLO bilan tahlil qilib, mashina zonaga kirganda
    on_cross(direction, ts) callback'ni chaqiradi."""

    def __init__(self, rtsp_url, zone, on_cross, det_cfg=None, name="detector"):
        self.rtsp = rtsp_url
        self.on_cross = on_cross
        self.name = name
        cfg = det_cfg or {}
        self.model_name = cfg.get("model", "yolov8n.pt")
        self.frame_skip = max(1, int(cfg.get("frame_skip", 4)))
        self.imgsz = int(cfg.get("imgsz", 640))
        self.conf = float(cfg.get("conf", 0.35))
        self.tracker = ZoneDirectionTracker(zone, cooldown=float(cfg.get("cooldown", 5)))
        self._running = False
        self._thread = None
        # PRE-ROLL buffer: detektor oqim kadrlarini ko'rib turadi — ularni
        # JPEG holida bufferlaymiz (kam xotira ~100KB/kadr), kesishda esa
        # kesishDAN OLDINGI soniyalar ham videoga tushadi. Aks holda video
        # kesish aniqlangach RTSP ochilib boshlanadi -> mashina o'tib bo'lgan.
        self.preroll_s = float(cfg.get("preroll_s", 5))
        self.postroll_s = float(cfg.get("postroll_s", 10))
        self.buf_fps = float(cfg.get("preroll_fps", 8))
        self._buf = deque()          # [(ts, jpeg_bytes)]
        self._buf_lock = threading.Lock()

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, name=self.name, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    @staticmethod
    def _cls_to_vtype(cls):
        if cls is None:
            return ""
        return _COCO_VTYPE.get(int(cls), "")

    def grab_frame(self, ts, tol=4.0):
        """Bufferdan ts vaqtiga eng yaqin kadrni (JPEG bytes) qaytaradi.
        Aktiv snapshot (kamera sekin bo'lsa mashina ketib bo'ladi) o'rniga —
        bu kadr AYNAN o'sha paytdagi mashinani ko'rsatadi (video bilan bir xil)."""
        with self._buf_lock:
            if not self._buf:
                return None
            best, best_d = None, tol
            for (bts, jpg) in self._buf:
                d = abs(bts - ts)
                if d <= best_d:
                    best, best_d = jpg, d
            return best

    def write_clip(self, out_path, center_ts, on_done=None, media_cfg=None):
        """PRE-ROLL klip: [center_ts - preroll, center_ts + postroll] oralig'idagi
        bufferlangan kadrlardan H.264 mp4 yasaydi (kesishDAN OLDINGI soniyalar
        ham tushadi). Fon threadда: postroll to'lguncha kutadi, so'ng yozadi.
        on_done(path|None) chaqiriladi. Buffer bo'sh bo'lsa None qaytaradi."""
        t = threading.Thread(target=self._write_clip_worker,
                             args=(out_path, center_ts, on_done, media_cfg or {}),
                             name=f"{self.name}-clip", daemon=True)
        t.start()

    def _write_clip_worker(self, out_path, center_ts, on_done, media_cfg):
        path = None
        try:
            # keyingi kadrlar (postroll) yig'ilguncha kutamiz
            wait_until = center_ts + self.postroll_s
            while self._running and time.time() < wait_until:
                time.sleep(0.2)
            lo, hi = center_ts - self.preroll_s, center_ts + self.postroll_s
            with self._buf_lock:
                frames = [j for (ts, j) in self._buf if lo <= ts <= hi]
            if len(frames) >= 3:
                path = self._encode_jpegs(frames, out_path, media_cfg)
        except Exception as e:
            print(f"[{self.name}] pre-roll klip xatosi: {e}")
        if on_done:
            try:
                on_done(path)
            except Exception:
                pass

    def _encode_jpegs(self, frames, out_path, media_cfg):
        """JPEG kadrlar ketma-ketligini ffmpeg orqali H.264 mp4 ga o'giradi
        (brauzer o'ynaydi). .part'ga yozib, tayyor bo'lgach atomik ko'chiradi."""
        import media as _media
        ffmpeg = _media.ffmpeg_exe()
        if not ffmpeg:
            return None
        part = out_path + ".part.mp4"
        mw = int(media_cfg.get("video_max_width", 1280))
        crf = str(media_cfg.get("video_crf", 28))
        cmd = [ffmpeg, "-y", "-nostdin", "-f", "image2pipe", "-framerate",
               str(self.buf_fps), "-c:v", "mjpeg", "-i", "-",
               "-c:v", "libx264", "-crf", crf, "-preset", "veryfast",
               "-pix_fmt", "yuv420p", "-vf", f"scale='min({mw},iw)':-2",
               "-movflags", "+faststart", part]
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            p.stdin.write(b"".join(frames))
            p.stdin.close()
            p.wait(timeout=60)
            if p.returncode == 0 and os.path.exists(part) and os.path.getsize(part) > 1000:
                os.replace(part, out_path)
                return out_path
        except Exception as e:
            print(f"[{self.name}] ffmpeg encode xatosi: {e}")
        try:
            if os.path.exists(part):
                os.remove(part)
        except Exception:
            pass
        return None

    def _diag(self, centers):
        """YOLO ko'rgan mashinalar (det_debug.log) — zona sozlash uchun.
        KARYER_DET_DEBUG=0 bilan o'chiriladi."""
        import os
        if os.environ.get("KARYER_DET_DEBUG", "1") == "0":
            return
        try:
            import datetime
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "det_debug.log")
            if os.path.exists(p) and os.path.getsize(p) > 1024 * 1024:
                return
            pts = " ".join(f"({c[0]:.2f},{c[1]:.2f})" for c in centers[:5])
            inz = sum(1 for c in centers if point_in_poly(c[0], c[1], self.tracker.poly))
            with open(p, "a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.now().strftime('%H:%M:%S')} "
                        f"[{self.name}] {len(centers)} ta, zonada={inz}: {pts}\n")
        except Exception:
            pass

    def _load(self):
        try:
            import cv2
        except ImportError:
            print(f"[{self.name}] opencv yo'q — zona detektori ishlamaydi")
            return None, None
        try:
            # torch default holda BARCHA yadrolarni band qiladi — 2 detektor
            # bilan CPU ~60% ga chiqib, video yozish/boshqa ishlarga xalaqit
            # beradi. 4 thread zona-kesish uchun bemalol yetadi.
            import torch
            torch.set_num_threads(4)
        except Exception:
            pass
        try:
            from ultralytics import YOLO
            model = YOLO(self.model_name)
        except Exception as e:
            print(f"[{self.name}] YOLO yuklanmadi ({e}) — zona detektori o'chirildi.")
            print(f"[{self.name}]   O'rnatish: pip install ultralytics")
            return cv2, None
        return cv2, model

    def _run(self):
        cv2, model = self._load()
        if cv2 is None or model is None:
            return

        # tahlillar orasidagi minimal oraliq — mashina zonani bir necha
        # soniyada kesadi, sekundiga ~3 tahlil bemalol yetadi; kichik oraliq
        # CPUni behuda to'ydiradi (latest-frame rejimida kadr o'tkazib
        # yuborilmaydi — doim eng yangisi tahlil qilinadi).
        min_interval = max(0.1, self.frame_skip * 0.1)

        # RTSP socket-timeout (mikrosekund): kamera qotib qolsa cap.read()
        # ABADIY osilmasin (kuzatildi: .31 half-open — detektor kadr olmay
        # kesish/videosiz qoldi). 15s jimlik -> read fail -> qayta ulanish.
        import os as _os
        _os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS",
                               "rtsp_transport;tcp|stimeout;15000000")
        while self._running:
            cap = cv2.VideoCapture(self.rtsp)
            if not cap.isOpened():
                print(f"[{self.name}] RTSP ochilmadi — 5s dan keyin qayta...")
                time.sleep(5)
                continue
            print(f"[{self.name}] Zona detektori ishlayapti (eng so'nggi kadr rejimi)")

            # ENG SO'NGGI KADR o'quvchisi: alohida oqim uzluksiz o'qib, faqat
            # oxirgi kadrni saqlaydi. Aks holda YOLO oqimdan sekin ishlasa
            # dekoder buferi to'lib, kesishlar 8-10s KECHIGIB keladi (kuzatildi).
            latest = {"frame": None, "dead": False}
            llock = threading.Lock()
            max_age = self.preroll_s + self.postroll_s + 3.0
            buf_interval = 1.0 / self.buf_fps if self.buf_fps > 0 else 0.125
            last_buf = [0.0]

            def _reader():
                while self._running and not latest["dead"]:
                    ok, f = cap.read()
                    if not ok:
                        latest["dead"] = True
                        return
                    with llock:
                        latest["frame"] = f
                    # PRE-ROLL: kadrni throttle bilan JPEG qilib bufferga
                    now = time.time()
                    if now - last_buf[0] >= buf_interval:
                        last_buf[0] = now
                        try:
                            ok2, jpg = cv2.imencode(".jpg", f,
                                                    [cv2.IMWRITE_JPEG_QUALITY, 70])
                            if ok2:
                                with self._buf_lock:
                                    self._buf.append((now, jpg.tobytes()))
                                    cut = now - max_age
                                    while self._buf and self._buf[0][0] < cut:
                                        self._buf.popleft()
                        except Exception:
                            pass

            rt = threading.Thread(target=_reader, name=f"{self.name}-rd", daemon=True)
            rt.start()

            last_diag = 0.0
            try:
                while self._running and not latest["dead"]:
                    with llock:
                        frame = latest["frame"]
                        latest["frame"] = None
                    if frame is None:
                        time.sleep(0.02)
                        continue
                    t0 = time.time()
                    h, w = frame.shape[:2]
                    res = model(frame, imgsz=self.imgsz, conf=self.conf,
                                classes=VEHICLE_CLASSES, verbose=False)
                    centers = []
                    big_cls, big_area = None, 0.0   # eng katta mashina klassi
                    for r in res:
                        if r.boxes is None:
                            continue
                        xyxy = r.boxes.xyxy.tolist()
                        clss = (r.boxes.cls.tolist()
                                if r.boxes.cls is not None else [None] * len(xyxy))
                        for box, cls in zip(xyxy, clss):
                            x1, y1, x2, y2 = box[:4]
                            # PASTKI-markaz (g'ildiraklar turgan nuqta) — zona
                            # YERDA chizilgan; baland mashinaning MARKAZI
                            # perspektivada zonadan tashqariga tushib, kesish
                            # o'tkazib yuborilardi.
                            centers.append(((x1 + x2) / 2 / w, y2 / h))
                            area = (x2 - x1) * (y2 - y1)
                            if area > big_area:
                                big_area, big_cls = area, cls
                    if centers:
                        now = time.time()
                        if now - last_diag >= 3.0:   # har 3s da bir (log to'lmasin)
                            last_diag = now
                            self._diag(centers)
                    # kadrdagi eng katta mashina klassi -> tur (car/truck/bus).
                    # Karyer'da tarozi yo'q — yo'nalish bilan birga TUR ham
                    # shu YOLO klassidan olinadi (raqamsiz hodisalar uchun).
                    vclass = self._cls_to_vtype(big_cls)
                    for direction, ts in self.tracker.update(centers, time.time()):
                        try:
                            self.on_cross(direction, ts, vclass)
                        except Exception as e:
                            print(f"[{self.name}] callback xatosi: {e}")
                    # tahlil juda tez tugasa — biroz kutamiz (CPU muvozanati)
                    spent = time.time() - t0
                    if spent < min_interval:
                        time.sleep(min_interval - spent)
            except Exception as e:
                print(f"[{self.name}] tahlil xatosi: {e}")
            finally:
                latest["dead"] = True
                cap.release()
            if self._running:
                time.sleep(2)
