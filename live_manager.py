#!/usr/bin/env python3
"""
LiveManager — serverdan kelgan (heartbeat javobidagi) jonli ko'rish
so'rovlarini bajaradi. Ikki rejim:

  snapshot : detektorning MAVJUD JPEG buferidan so'nggi kadr olinadi va
             POST /api/local/live-snapshot ga yuboriladi. Kameraga YANGI
             RTSP sessiya ochilmaydi, CPU ~0 — 144 kbps internetda ham ishlaydi.
  video    : ffmpeg SUB-oqimni transkodlashsiz (-c copy) serverdagi
             MediaMTX'ga push qiladi.

Har so'rov TTL bilan keladi; server so'rovni yangilab turmasa (tomoshabin
ketdi) sessiya o'zi to'xtaydi. USTUVORLIK: outbox'da yuborilmagan hodisa
bo'lsa snapshot yuborish to'xtab turadi, video sessiya boshlanmaydi —
hodisa har doim jonli ko'rinishdan muhim.

MUHIM: bu modul faqat heartbeat orqali (live.enabled=true) chaqiriladi;
o'chiq holatda umuman ishlamaydi.
"""

import time
import threading
import subprocess

try:
    import requests
except ImportError:
    requests = None

import db
import media

# hodisa navbati bo'shashini kutish (video sessiya boshlashdan oldin)
QUEUE_WAIT_S = 5
# ffmpeg o'z-o'zidan o'lsa qayta urinish oralig'i
FFMPEG_RETRY_S = 5


class _Session:
    def __init__(self, camera_code, mode):
        self.camera_code = camera_code
        self.mode = mode          # "snapshot" | "video"
        self.until = 0.0          # TTL muddati (epoch)
        self.thread = None
        self.proc = None          # video rejimda ffmpeg jarayoni
        self.publish_url = ""
        self.snapshot_interval = 3.0


class LiveManager:
    def __init__(self, cfg, stations):
        server = cfg.get("server", {}) or {}
        self.url = (server.get("url") or "").rstrip("/")
        self.api_key = server.get("api_key", "")
        self.stations = stations
        self._sessions = {}       # camera_code -> _Session
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ jamoat
    def handle_requests(self, live_requests):
        """Heartbeat javobidagi so'rovlar: bor sessiyalarning TTL'ini yangilaydi,
        yangilarini ochadi. So'ralmagan/muddati o'tganlar o'zi to'xtaydi."""
        now = time.time()
        for req in live_requests:
            code = (req.get("camera_code") or "").strip()
            if not code:
                continue
            mode = req.get("mode") or "snapshot"
            if mode == "auto":
                mode = "snapshot"   # v1: auto = snapshot (video serverda aniq so'raladi)
            ttl = float(req.get("ttl_s", 45))
            with self._lock:
                s = self._sessions.get(code)
                if s is None or s.thread is None or not s.thread.is_alive():
                    s = _Session(code, mode)
                    self._sessions[code] = s
                    s.until = now + ttl
                    s.publish_url = self._publish_url(req)
                    s.snapshot_interval = float(req.get("snapshot_interval_s", 3))
                    s.thread = threading.Thread(
                        target=self._run_session, args=(s,),
                        name=f"live-{code}", daemon=True)
                    s.thread.start()
                else:
                    s.until = now + ttl   # TTL yangilash — davom etaveradi

    def active_summary(self):
        """Heartbeat payload uchun: hozir nima uzatilyapti."""
        with self._lock:
            return [{"camera_code": s.camera_code, "mode": s.mode}
                    for s in self._sessions.values()
                    if s.thread is not None and s.thread.is_alive()]

    def stop_all(self):
        with self._lock:
            for s in self._sessions.values():
                s.until = 0   # threadlar o'zi chiqadi
                if s.proc is not None:
                    try:
                        s.proc.terminate()
                    except Exception:
                        pass
            self._sessions = {}

    # ------------------------------------------------------------------ ichki
    @staticmethod
    def _publish_url(req):
        url = (req.get("publish_url") or "").strip()
        tok = (req.get("publish_token") or "").strip()
        if url and tok:
            url += ("&" if "?" in url else "?") + "token=" + tok
        return url

    def _find_station(self, camera_code):
        """camera_code bo'yicha stansiyani topadi. Kod plate yoki record
        kameraga tegishli bo'lishi mumkin — jonli ko'rinish har doim shu
        stansiyaning VIDEO kamerasidan beriladi (detektor buferi/SUB o'sha yerda)."""
        for st in self.stations:
            cfg = getattr(st, "cfg", {}) or {}
            codes = {
                (cfg.get("video", {}) or {}).get("code", ""),
                (cfg.get("anpr", {}) or {}).get("code", ""),
                cfg.get("camera_name", ""),
            }
            if camera_code in codes:
                return st
        return None

    def _run_session(self, s):
        st = self._find_station(s.camera_code)
        if st is None:
            print(f"[live] {s.camera_code}: mos stansiya topilmadi — e'tiborsiz")
            return
        print(f"[live] {s.camera_code}: {s.mode} sessiya boshlandi")
        try:
            if s.mode == "video" and s.publish_url:
                self._video_loop(s, st)
            else:
                self._snapshot_loop(s, st)
        finally:
            with self._lock:
                if self._sessions.get(s.camera_code) is s:
                    del self._sessions[s.camera_code]
            print(f"[live] {s.camera_code}: sessiya tugadi")

    # ---------------------------------------------------- snapshot rejimi
    def _snapshot_loop(self, s, st):
        if requests is None:
            return
        snap_url = f"{self.url}/api/local/live-snapshot"
        while time.time() < s.until:
            # USTUVORLIK: hodisa navbati bo'sh bo'lmasa — kadr yubormay turamiz
            try:
                busy = db.pending_count() > 0
            except Exception:
                busy = False
            if not busy:
                det = getattr(st, "detector", None)
                jpg = None
                if det is not None:
                    try:
                        jpg = det.latest_jpeg()
                    except Exception:
                        jpg = None
                if jpg:
                    try:
                        requests.post(
                            snap_url, data=jpg, timeout=10,
                            headers={"X-API-Key": self.api_key,
                                     "X-Camera-Code": s.camera_code,
                                     "Content-Type": "image/jpeg"})
                    except Exception:
                        pass   # tarmoq xatosi — keyingi kadrgacha jim
            time.sleep(max(1.0, s.snapshot_interval))

    # ---------------------------------------------------- video rejimi
    def _video_loop(self, s, st):
        rtsp = getattr(st, "rtsp_sub", "") or getattr(st, "rtsp", "")
        if not rtsp:
            print(f"[live] {s.camera_code}: RTSP manzil yo'q — video rejim ishlamaydi")
            return
        ff = media.ffmpeg_exe()
        if not ff:
            print(f"[live] {s.camera_code}: ffmpeg topilmadi")
            return
        while time.time() < s.until:
            # hodisa navbati bo'shashini kutamiz — event trafigi ustuvor
            waited = 0
            while db.pending_count() > 0 and time.time() < s.until and waited < 60:
                time.sleep(QUEUE_WAIT_S)
                waited += QUEUE_WAIT_S
            if time.time() >= s.until:
                break
            cmd = [ff, "-nostdin", "-loglevel", "error",
                   "-rtsp_transport", "tcp", "-i", rtsp,
                   "-c", "copy", "-an",
                   "-f", "rtsp", "-rtsp_transport", "tcp", s.publish_url]
            try:
                s.proc = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                print(f"[live] {s.camera_code}: ffmpeg ishga tushmadi: {e}")
                return
            # TTL tugashini yoki jarayon o'limini kutamiz
            while time.time() < s.until:
                if s.proc.poll() is not None:
                    break   # ffmpeg o'ldi — qayta uriniladi
                time.sleep(1)
            if s.proc.poll() is None:
                try:
                    s.proc.terminate()
                    s.proc.wait(timeout=5)
                except Exception:
                    try:
                        s.proc.kill()
                    except Exception:
                        pass
                break   # TTL tugadi — chiqamiz
            time.sleep(FFMPEG_RETRY_S)
        s.proc = None
