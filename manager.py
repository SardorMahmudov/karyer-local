#!/usr/bin/env python3
"""
StationManager — barcha stansiyalar va outbox yuboruvchini boshqaradi.

start_all() / stop_all() / restart() — bloklaydigan sikldan xoli, shuning uchun
ham konsol (main.py), ham tray xizmati (tray.py) ishlatadi.
"""

import os
import json
import time
import uuid
import threading

import db
import config as cfgmod
from api_client import ApiClient
from outbox import OutboxSender
from station import make_station

BASE_DIR = cfgmod.app_dir()

# media (rasm/video) fayllari shu kundan eski bo'lsa o'chiriladi — disk to'lmasin.
# Hodisalarning o'zi (baza + serverdagi nusxa) saqlanadi, faqat lokal fayl o'chadi.
MEDIA_KEEP_DAYS = 14


def _abs(path):
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)


def _recover_unsent(cfg):
    """Eski versiya restart paytida navbatga tushirmay qoldirgan hodisalarni
    (bazada bor, outbox'da yo'q) qayta navbatga qo'yadi. Payload weigh_events
    qatoridan tiklanadi; camera_name/is_main stansiya configidan olinadi."""
    st_map = {}
    for s in cfg.get("stations", []):
        st_map[s.get("name")] = (s.get("camera_name") or s.get("name"),
                                 bool(s.get("is_main")))
    try:
        rows = db.fetch_unqueued_events(days=3)
    except Exception as e:
        print(f"[recover] baza xatosi: {e}")
        return 0
    n = 0
    for (eid, quarry_id, station, plate, direction, weight,
         unit, event_time, video_path, image_paths) in rows:
        cam, is_main = st_map.get(station, (station, False))
        if video_path and not os.path.exists(video_path):
            video_path = None   # fayl yo'q — kutmaymiz
        try:
            imgs = json.loads(image_paths or "[]")
        except Exception:
            imgs = []
        payload = {
            "event_uid": str(uuid.uuid4()),
            "quarry_id": quarry_id,
            "camera_name": cam,
            "is_main": is_main,
            "plate": plate,
            "direction": direction,
            "weight": weight,
            "unit": unit or "kg",
            "event_time": event_time,
            "video_path": video_path,
            "image_paths": [p for p in imgs if os.path.exists(p)],
        }
        db.enqueue_outbox(eid, payload)
        n += 1
    if n:
        print(f"[recover] {n} ta yuborilmay qolgan hodisa navbatga qayta qo'yildi")
    return n


def _cleanup_media_loop(dirs, keep_days=MEDIA_KEEP_DAYS, interval_h=12):
    """Har 12 soatda eski media fayllarni o'chiradi (fon oqimi, dastur bilan yashaydi)."""
    def _once():
        cutoff = time.time() - keep_days * 86400
        removed = 0
        for d in dirs:
            if not os.path.isdir(d):
                continue
            for name in os.listdir(d):
                p = os.path.join(d, name)
                try:
                    if os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                        os.remove(p)
                        removed += 1
                except OSError:
                    pass
        if removed:
            print(f"[media] {removed} ta eski fayl tozalandi (> {keep_days} kun)")

    def _run():
        while True:
            try:
                _once()
                db.prune_sent(days=30)
            except Exception as e:
                print(f"[media] tozalash xatosi: {e}")
            time.sleep(interval_h * 3600)

    t = threading.Thread(target=_run, name="media-cleanup", daemon=True)
    t.start()
    return t


class StationManager:
    def __init__(self, sim=False):
        self.sim = sim
        self.stations = []
        self.sender = None
        self.running = False
        self.quarry_id = ""
        self.live = None        # LiveManager (live.enabled=true bo'lsagina)
        self.heartbeat = None   # HeartbeatSender

    def start_all(self, cfg=None):
        """config bo'yicha stansiyalar + outboxni ishga tushiradi."""
        if self.running:
            return
        cfg = cfg or cfgmod.load_config() or cfgmod.default_config()

        db.init_db()
        _recover_unsent(cfg)   # restartda yo'qolgan hodisalarni qayta navbatga

        save_dir = _abs(cfg.get("save_dir", "captures"))
        video_dir = _abs(cfg.get("video_dir", "videos"))
        # media retention — birinchi start'da bir marta boshlaymiz (restartda emas)
        if not getattr(StationManager, "_cleanup_started", False):
            StationManager._cleanup_started = True
            _cleanup_media_loop([save_dir, video_dir])
        self.quarry_id = cfg.get("quarry_id", "")
        media_cfg = cfg.get("media", cfgmod.default_media())

        self.sender = OutboxSender(ApiClient(cfg.get("server", {})))
        self.sender.start()

        self.stations = []
        for st_cfg in cfg.get("stations", []):
            st = make_station(st_cfg, self.quarry_id, save_dir, video_dir,
                              sim=self.sim, media_cfg=media_cfg)
            st.start()
            self.stations.append(st)

        self.running = True

        # --- LIVE (ixtiyoriy, default O'CHIQ) -------------------------------
        # live.enabled=false bo'lsa hech narsa ishga tushmaydi; har qanday
        # xato asosiy oqimni (stansiyalar/outbox) buza olmasligi uchun try ichida.
        try:
            if (cfg.get("live") or {}).get("enabled"):
                from live_manager import LiveManager
                from heartbeat import HeartbeatSender
                self.live = LiveManager(cfg, self.stations)
                self.heartbeat = HeartbeatSender(cfg, self, self.live)
                self.heartbeat.start()
        except Exception as e:
            print(f"[live] modul ishga tushmadi (asosiy ishga ta'sir yo'q): {e}")
            self.live = None
            self.heartbeat = None

        print(f"✅ {len(self.stations)} ta stansiya ishlayapti | "
              f"karyer={self.quarry_id} | {'SIM' if self.sim else 'REAL'} rejim")
        return len(self.stations)

    def stop_all(self):
        """Barcha stansiyalar va outboxni to'xtatadi."""
        if not self.running:
            return
        if self.heartbeat:
            try:
                self.heartbeat.stop()
            except Exception:
                pass
            self.heartbeat = None
        if self.live:
            try:
                self.live.stop_all()
            except Exception:
                pass
            self.live = None
        for st in self.stations:
            try:
                st.stop()
            except Exception as e:
                print(f"stansiya to'xtatishda xato: {e}")
        if self.sender:
            self.sender.stop()
        self.stations = []
        self.sender = None
        self.running = False
        print("⏸ To'xtatildi")

    def restart(self, cfg=None):
        """Sozlamalar o'zgargach yangi config bilan qayta ishga tushiradi."""
        self.stop_all()
        return self.start_all(cfg)

    def status(self):
        return {
            "running": self.running,
            "stations": len(self.stations),
            "quarry_id": self.quarry_id,
            "pending": db.pending_count() if self.running else 0,
        }
