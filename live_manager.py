#!/usr/bin/env python3
"""
LiveManager — jonli ko'rish (server sozlamasi bilan boshqariladi).

Server kontrakti (raqamli-karyer, backend/app/api/agent.py + services/live.py):
  * adminkada live_stream_enabled / video_quality o'zgartiriladi;
  * agent buni heartbeat javobidagi config'dan oladi va shu yerga uzatadi;
  * snapshot rejim: POST /api/agent/live-snapshot (Bearer, X-Camera-Id, JPEG);
  * video rejim: ffmpeg SUB-oqimni MediaMTX'ga push qiladi — manzil
    GET /api/agent/config -> live_stream.push_url / path_template
    (yo'l: karyer_<kod>_<kamera>, login-parol URL ichida).

Rejim tanlash (video_quality):
  "snapshot" yoki "auto" -> JPEG kadrlar (detektor buferidan, yangi RTSP
      sessiyasiz — 144 kbps kanalda ham ishlaydi; "auto"da kanal o'lchash
      keyingi versiyada, hozircha xavfsiz tomonga: snapshot).
  "low"/"medium"/"high" -> MediaMTX push (SUB-oqim -c copy, transkodlashsiz —
      profil bitrate'lari kamera SUB sozlamasi bilan belgilanadi).

USTUVORLIK: outbox'da yuborilmagan hodisa bo'lsa snapshot to'xtab turadi,
video push boshlanmaydi — hodisa har doim jonli ko'rinishdan muhim.
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

SNAPSHOT_INTERVAL_S = 3
QUEUE_WAIT_S = 5
FFMPEG_RETRY_S = 5
VIDEO_QUALITIES = ("low", "medium", "high")


class _Session:
    def __init__(self, camera_id, mode):
        self.camera_id = camera_id
        self.mode = mode          # "snapshot" | "video"
        self.active = True        # False -> thread o'zi chiqadi
        self.thread = None
        self.proc = None


class LiveManager:
    def __init__(self, cfg, stations):
        server = cfg.get("server", {}) or {}
        live = cfg.get("live", {}) or {}
        self.url = (server.get("url") or "").rstrip("/")
        self.token = (live.get("agent_token") or "").strip()
        self.stations = stations
        self._sessions = {}       # camera_id -> _Session
        self._lock = threading.Lock()
        self._live_stream = None  # {push_url, path_template}
        self._quality = ""

    # ------------------------------------------------------------------ boshqaruv
    def apply(self, config, live_stream):
        """Heartbeat'dan chaqiriladi: server sozlamasiga qarab sessiyalarni
        ochadi/yopadi. Bir xil holatda qayta chaqirilsa hech narsa qilmaydi."""
        self._live_stream = live_stream or self._live_stream
        enabled = bool(config.get("live_stream_enabled", False))
        quality = str(config.get("video_quality") or "auto")
        self._quality = quality

        if not enabled:
            self.stop_all()
            return

        mode = "video" if quality in VIDEO_QUALITIES else "snapshot"
        if mode == "video" and not self._push_base():
            # MediaMTX sozlanmagan — server None berdi; snapshot'ga tushamiz
            mode = "snapshot"

        want = {}   # camera_id -> (mode, station)
        for st in self.stations:
            cfg = getattr(st, "cfg", {}) or {}
            vid = cfg.get("video", {}) or {}
            cam_id = vid.get("code") or cfg.get("camera_name") or cfg.get("name") or ""
            if cam_id:
                want[cam_id] = (mode, st)

        with self._lock:
            # ortiqcha/rejimi o'zgargan sessiyalarni yopamiz
            for cam_id, s in list(self._sessions.items()):
                tgt = want.get(cam_id)
                if tgt is None or tgt[0] != s.mode:
                    self._stop_session(s)
                    del self._sessions[cam_id]
            # yetishmayotganlarini ochamiz
            for cam_id, (m, st) in want.items():
                cur = self._sessions.get(cam_id)
                if cur is not None and cur.thread is not None and cur.thread.is_alive():
                    continue
                s = _Session(cam_id, m)
                self._sessions[cam_id] = s
                s.thread = threading.Thread(
                    target=self._run_session, args=(s, st),
                    name=f"live-{cam_id}", daemon=True)
                s.thread.start()

    def state_summary(self):
        """Heartbeat payload uchun: (live_streaming, current_quality)."""
        with self._lock:
            alive = [s for s in self._sessions.values()
                     if s.thread is not None and s.thread.is_alive()]
        if not alive:
            return False, ""
        if any(s.mode == "video" for s in alive):
            return True, self._quality if self._quality in VIDEO_QUALITIES else "low"
        return True, "snapshot"

    def stop_all(self):
        with self._lock:
            for s in self._sessions.values():
                self._stop_session(s)
            self._sessions = {}

    @staticmethod
    def _stop_session(s):
        s.active = False
        if s.proc is not None:
            try:
                s.proc.terminate()
            except Exception:
                pass

    # ------------------------------------------------------------------ ichki
    def _push_base(self):
        """MediaMTX bazaviy manzili (creds bilan): push_url'dan yo'lni kesib."""
        ls = self._live_stream or {}
        push = (ls.get("push_url") or "").strip()
        if not push:
            return ""
        return push.rsplit("/", 1)[0]

    def _push_url_for(self, camera_id):
        ls = self._live_stream or {}
        base = self._push_base()
        tpl = (ls.get("path_template") or "").strip()
        if not base:
            return ""
        if tpl and "{camera_id}" in tpl:
            return f"{base}/{tpl.format(camera_id=camera_id)}"
        return f"{base}/{camera_id}"

    def _run_session(self, s, st):
        print(f"[live] {s.camera_id}: {s.mode} boshlandi")
        try:
            if s.mode == "video":
                self._video_loop(s, st)
            else:
                self._snapshot_loop(s, st)
        finally:
            print(f"[live] {s.camera_id}: to'xtadi")

    # ---------------------------------------------------- snapshot rejimi
    def _snapshot_loop(self, s, st):
        if requests is None:
            return
        snap_url = f"{self.url}/api/agent/live-snapshot"
        headers = {"Authorization": f"Bearer {self.token}",
                   "X-Camera-Id": s.camera_id,
                   "Content-Type": "image/jpeg"}
        while s.active:
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
                        requests.post(snap_url, data=jpg, headers=headers, timeout=10)
                    except Exception:
                        pass   # tarmoq xatosi — keyingi kadrgacha jim
            time.sleep(SNAPSHOT_INTERVAL_S)

    # ---------------------------------------------------- video rejimi
    def _video_loop(self, s, st):
        rtsp = getattr(st, "rtsp_sub", "") or getattr(st, "rtsp", "")
        if not rtsp:
            print(f"[live] {s.camera_id}: RTSP manzil yo'q")
            return
        ff = media.ffmpeg_exe()
        if not ff:
            print(f"[live] {s.camera_id}: ffmpeg topilmadi")
            return
        push = self._push_url_for(s.camera_id)
        if not push:
            print(f"[live] {s.camera_id}: MediaMTX manzili yo'q")
            return
        while s.active:
            # hodisa navbati ustuvor — bo'shashini kutamiz (maks 60s)
            waited = 0
            while s.active and waited < 60:
                try:
                    if db.pending_count() == 0:
                        break
                except Exception:
                    break
                time.sleep(QUEUE_WAIT_S)
                waited += QUEUE_WAIT_S
            if not s.active:
                break
            cmd = [ff, "-nostdin", "-loglevel", "error",
                   "-rtsp_transport", "tcp", "-i", rtsp,
                   "-c", "copy", "-an",
                   "-f", "rtsp", "-rtsp_transport", "tcp", push]
            try:
                s.proc = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                print(f"[live] {s.camera_id}: ffmpeg xatosi: {e}")
                return
            while s.active and s.proc.poll() is None:
                time.sleep(1)
            if s.proc.poll() is None:   # active=False bo'ldi — to'xtatamiz
                try:
                    s.proc.terminate()
                    s.proc.wait(timeout=5)
                except Exception:
                    try:
                        s.proc.kill()
                    except Exception:
                        pass
            s.proc = None
            if s.active:
                time.sleep(FFMPEG_RETRY_S)   # ffmpeg o'ldi — qayta urinamiz
