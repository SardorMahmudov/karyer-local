#!/usr/bin/env python3
"""
Heartbeat — serverga davriy holat yuborish va sozlamani qabul qilish.

Server kontrakti (raqamli-karyer doc.txt §3.2–3.3, backend/app/api/agent.py):

    POST {url}/api/agent/heartbeat      Authorization: Bearer <agent-token>
      body : {agent_version, scale_ok, cameras:[{id,ok}], queue_size,
              upload_kbps_avg, live_streaming, current_quality}
      javob: {ok, server_time, config:{video_quality, live_stream_enabled,
              heartbeat_interval_sec, ...}}

    GET {url}/api/agent/config          (davriy, ~60s)
      javob: config + live_stream:{push_url, path_template} — MediaMTX manzili.

Jonli ko'rish BUYRUQ bilan emas, SOZLAMA bilan boshqariladi: adminkada
live_stream_enabled/video_quality o'zgartiriladi, agent keyingi heartbeat'da
ko'rib LiveManager'ga uzatadi.

Agent-token adminkada beriladi (KRY_...) va config.json live.agent_token'ga
BIR MARTA yoziladi. MUHIM: live.enabled=true bo'lmaguncha bu modul HECH NARSA
qilmaydi — ishlab turgan tizim xatti-harakati o'zgarmaydi.
"""

import time
import threading

try:
    import requests
except ImportError:
    requests = None

import db

AGENT_VERSION = "1.2.0-live"

DEFAULT_INTERVAL_S = 60      # server config kelguncha
CONFIG_REFRESH_S = 60        # live_stream (push_url) yangilash oralig'i
ERROR_INTERVAL_S = 60        # tarmoq/401 xatosida kutish


class HeartbeatSender:
    def __init__(self, cfg, manager, live_manager=None):
        server = cfg.get("server", {}) or {}
        live = cfg.get("live", {}) or {}
        self.url = (server.get("url") or "").rstrip("/")
        self.token = (live.get("agent_token") or "").strip()
        # DEFAULT O'CHIQ — faqat live.enabled=true va token bor bo'lsa ishlaydi
        self.enabled = (bool(live.get("enabled", False))
                        and bool(self.url) and bool(self.token)
                        and requests is not None)
        self.manager = manager
        self.live = live_manager
        self.interval = DEFAULT_INTERVAL_S
        self._running = False
        self._thread = None
        self._warned = set()      # bir xil ogohlantirish qayta yozilmasin
        self._last_cfg_fetch = 0.0
        self._live_stream = None  # GET /agent/config dagi live_stream bloki
        # yoqilgan-u token kiritilmagan — foydalanuvchiga bir marta aytamiz
        self._token_missing = (bool(live.get("enabled", False))
                               and bool(self.url) and not self.token)

    # ------------------------------------------------------------------ start/stop
    def start(self):
        if not self.enabled:
            if self._token_missing:
                print("[heartbeat] live.enabled=true, lekin live.agent_token yo'q — "
                      "adminkadan (karyer sahifasi -> Agent) token olib config'ga yozing")
            return False
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(target=self._run, name="heartbeat", daemon=True)
        self._thread.start()
        print(f"[heartbeat] yoqildi: {self.url}/api/agent/heartbeat")
        return True

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------ payload
    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _cameras_state(self):
        """Video kameralar holati — id sifatida server kamera KODI ishlatiladi
        (saytdagi jonli ko'rinish/DB fallback shu kodlar bilan ishlaydi)."""
        cams = []
        for st in getattr(self.manager, "stations", []):
            cfg = getattr(st, "cfg", {}) or {}
            vid = cfg.get("video", {}) or {}
            cam_id = vid.get("code") or cfg.get("camera_name") or cfg.get("name") or ""
            if not cam_id:
                continue
            ok = False
            det = getattr(st, "detector", None)
            if det is not None:
                try:
                    ok = det.latest_jpeg(max_age_s=15.0) is not None
                except Exception:
                    pass
            cams.append({"id": cam_id, "ok": ok})
        return cams

    def _scale_ok(self):
        """Tarozili stansiyalarda so'nggi 30s ichida o'qish bo'lganmi.
        Tarozi umuman yo'q (kon) bo'lsa ham False — server buni ko'rsatmaydi."""
        for st in getattr(self.manager, "stations", []):
            reader = getattr(st, "scale", None)
            if reader is not None and time.time() - getattr(reader, "last_ts", 0) <= 30:
                return True
        return False

    def _payload(self):
        pending = 0
        try:
            pending = db.pending_count()
        except Exception:
            pass
        live_streaming, quality = False, ""
        if self.live is not None:
            try:
                live_streaming, quality = self.live.state_summary()
            except Exception:
                pass
        return {
            "agent_version": AGENT_VERSION,
            "scale_ok": self._scale_ok(),
            "cameras": self._cameras_state(),
            "queue_size": pending,
            "upload_kbps_avg": 0,   # o'lchash keyingi versiyada
            "live_streaming": live_streaming,
            "current_quality": quality,
        }

    # ------------------------------------------------------------------ server bilan
    def _fetch_live_stream(self):
        """GET /api/agent/config — live_stream (MediaMTX push manzili) uchun."""
        try:
            r = requests.get(f"{self.url}/api/agent/config",
                             headers=self._headers(), timeout=10)
            if r.status_code == 200:
                data = r.json() or {}
                self._live_stream = data.get("live_stream") or None
                self._last_cfg_fetch = time.time()
        except Exception:
            pass

    def _apply(self, config):
        """Heartbeat javobidagi config: interval + live boshqaruvi."""
        try:
            iv = int(config.get("heartbeat_interval_sec") or 0)
            if 10 <= iv <= 3600:
                self.interval = iv
        except Exception:
            pass
        if self.live is not None:
            try:
                self.live.apply(config, self._live_stream)
            except Exception as e:
                self._warn("live-apply", f"[live] sozlamani qo'llashda xato: {e}")

    def _warn(self, key, msg):
        if key not in self._warned:
            self._warned.add(key)
            print(msg)

    def _run(self):
        while self._running:
            wait = self.interval
            try:
                # push_url'ni davriy yangilab turamiz (birinchi marta darhol)
                if (self._live_stream is None
                        or time.time() - self._last_cfg_fetch > CONFIG_REFRESH_S):
                    self._fetch_live_stream()

                r = requests.post(f"{self.url}/api/agent/heartbeat",
                                  json=self._payload(),
                                  headers=self._headers(), timeout=10)
                if r.status_code == 200:
                    self._warned.discard("http")
                    try:
                        data = r.json() or {}
                    except ValueError:
                        data = {}
                    self._apply(data.get("config") or {})
                elif r.status_code == 401:
                    self._warn("http", "[heartbeat] token yaroqsiz/bekor qilingan (401) — "
                                       "adminkadan yangi token oling")
                    wait = ERROR_INTERVAL_S
                elif r.status_code == 404:
                    self._warn("http", "[heartbeat] server endpointi topilmadi (404) — "
                                       "server versiyasi eskimi?")
                    wait = ERROR_INTERVAL_S * 2
                else:
                    wait = ERROR_INTERVAL_S
            except Exception:
                # tarmoq yo'q — normal, jim kutamiz
                wait = ERROR_INTERVAL_S
            time.sleep(wait)
