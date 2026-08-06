#!/usr/bin/env python3
"""
Heartbeat — serverga davriy holat yuborish va undan LIVE buyruqlarini olish.

Localga tashqaridan kirib bo'lmaydi (NAT), shuning uchun server buyruqlari
(masalan "falon kamerani jonli uzat") heartbeat JAVOBIDA keladi:

    POST {server.url}/api/local/heartbeat   (X-API-Key)
    javob: {"live_requests": [{"camera_code", "mode", "publish_url",
                               "publish_token", "snapshot_interval_s", "ttl_s"}]}

MUHIM: config'da live.enabled=true bo'lmaguncha bu modul HECH NARSA qilmaydi —
ishlab turgan tizim xatti-harakati o'zgarmaydi. Server endpointi hali tayyor
bo'lmasa (404) — jimgina kutadi, hech narsani buzmaydi.
"""

import time
import threading

try:
    import requests
except ImportError:
    requests = None

import db

AGENT_VERSION = "1.1.0-live"

# server 404 qaytarsa (endpoint hali yozilmagan) — shu intervalga sekinlashamiz
NOT_READY_INTERVAL_S = 120


class HeartbeatSender:
    def __init__(self, cfg, manager, live_manager=None):
        server = cfg.get("server", {}) or {}
        live = cfg.get("live", {}) or {}
        self.url = (server.get("url") or "").rstrip("/")
        self.api_key = server.get("api_key", "")
        self.interval = float(live.get("heartbeat_interval_s", 15))
        # DEFAULT O'CHIQ — faqat config'da live.enabled=true bo'lsa ishlaydi
        self.enabled = (bool(live.get("enabled", False))
                        and bool(self.url) and bool(self.api_key)
                        and requests is not None)
        self.manager = manager
        self.live = live_manager
        self._running = False
        self._thread = None
        self._warned_not_ready = False
        self._start_ts = time.time()

    # ------------------------------------------------------------------ start/stop
    def start(self):
        if not self.enabled:
            return False   # live o'chiq — thread ham ochilmaydi
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(target=self._run, name="heartbeat", daemon=True)
        self._thread.start()
        print(f"[heartbeat] yoqildi — har {self.interval:.0f}s: {self.url}/api/local/heartbeat")
        return True

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------ payload
    def _stations_status(self):
        out = []
        for st in getattr(self.manager, "stations", []):
            cfg = getattr(st, "cfg", {}) or {}
            det = getattr(st, "detector", None)
            video_ok = False
            if det is not None:
                try:
                    # bufferda so'nggi 15s ichida kadr bo'lsa — video oqim tirik
                    video_ok = det.latest_jpeg(max_age_s=15.0) is not None
                except Exception:
                    pass
            out.append({
                "name": cfg.get("name", ""),
                "post_code": cfg.get("post_code", ""),
                "video_ok": video_ok,
            })
        return out

    def _payload(self):
        p = {
            "agent_version": AGENT_VERSION,
            "uptime_s": int(time.time() - self._start_ts),
            "stations": self._stations_status(),
            "outbox_pending": 0,
            "live_active": [],
        }
        try:
            p["outbox_pending"] = db.pending_count()
        except Exception:
            pass
        if self.live is not None:
            try:
                p["live_active"] = self.live.active_summary()
            except Exception:
                pass
        return p

    # ------------------------------------------------------------------ loop
    def _run(self):
        while self._running:
            interval = self.interval
            try:
                r = requests.post(
                    f"{self.url}/api/local/heartbeat",
                    json=self._payload(),
                    headers={"X-API-Key": self.api_key},
                    timeout=10,
                )
                if r.status_code == 404:
                    # server tomonida endpoint hali yozilmagan — kutamiz
                    if not self._warned_not_ready:
                        self._warned_not_ready = True
                        print("[heartbeat] server endpointi hali tayyor emas (404) — "
                              f"{NOT_READY_INTERVAL_S}s interval bilan kutaman")
                    interval = NOT_READY_INTERVAL_S
                elif r.status_code == 200:
                    if self._warned_not_ready:
                        self._warned_not_ready = False
                        print("[heartbeat] server endpointi ishga tushdi")
                    if self.live is not None:
                        try:
                            data = r.json() or {}
                        except ValueError:
                            data = {}
                        self.live.handle_requests(data.get("live_requests") or [])
                else:
                    print(f"[heartbeat] HTTP {r.status_code}: {r.text[:120]}")
            except Exception as e:
                # tarmoq yo'q — normal holat, indamay keyingi urinish
                if self._warned_not_ready is False:
                    pass
                interval = max(self.interval, 30)
            time.sleep(interval)
