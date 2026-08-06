#!/usr/bin/env python3
"""
Server bilan aloqa — hodisani serverga yuboradi.

Ikki format (config.server.send_files bilan tanlanadi):
  - multipart : rasm + video FAYLNING O'ZI yuboriladi (data=JSON + fayllar)  [default]
  - json      : faqat matn + fayl yo'llari

Yuborish/retry mantig'i outbox.py da; bu yerda faqat bitta yuborish.
"""

import os
import json
import datetime

try:
    import requests
except ImportError:
    requests = None

# video shu muddatdan ko'p kutilsa — videosiz yuboriladi (hodisa yo'qolmasin)
VIDEO_WAIT_MAX_S = 600
# rasm kutish oynasi — station late-image tekshiruvlari (30/60/90s) dan sal katta
IMAGE_WAIT_MAX_S = 100


def _event_age_s(payload):
    """Hodisa yoshi (soniya) — event_time UZ mahalliy vaqtda yoziladi,
    mashina soati ham UZ vaqti. Parse bo'lmasa 'juda eski' deb qaytariladi
    (abadiy kutishdan ko'ra videosiz yuborish afzal)."""
    try:
        t = datetime.datetime.strptime(payload.get("event_time", ""), "%Y-%m-%d %H:%M:%S")
        return (datetime.datetime.now() - t).total_seconds()
    except Exception:
        return 10 ** 9


class ApiClient:
    def __init__(self, server_cfg):
        self.url = (server_cfg.get("url") or "").rstrip("/")
        self.api_key = server_cfg.get("api_key", "")
        self.enabled = server_cfg.get("enabled", False)
        self.endpoint = server_cfg.get("endpoint", "/api/weigh")
        # true -> multipart (rasm/video fayl bilan), false -> faqat JSON
        self.send_files = server_cfg.get("send_files", True)
        # false -> rasm (ANPR snapshot) yuborilmaydi, faqat video + matn ketadi.
        # (Server rasm ingest'i material seed'siz 500 berganda vaqtincha ishlatiladi.)
        self.send_images = server_cfg.get("send_images", True)

    @property
    def _full_url(self):
        return f"{self.url}{self.endpoint}"

    def _headers(self):
        return {"X-API-Key": self.api_key}

    def send(self, payload):
        """
        payload'ni serverga yuboradi. Qaytaradi: (ok: bool, info: str).

        Agar video kutilyotgan bo'lsa-yu fayl hali tayyor bo'lmasa —
        (False, ...) qaytaradi, outbox keyinroq qayta urinadi (tayyor bo'lguncha).
        """
        if not self.enabled:
            return False, "server o'chirilgan (config.enabled=false)"
        if requests is None:
            return False, "requests kutubxonasi yo'q"
        if not self.url:
            return False, "server URL yo'q"

        if self.send_files:
            return self._send_multipart(payload)
        return self._send_json(payload)

    # ---------- JSON (fayl yo'lsiz) ----------
    def _send_json(self, payload):
        try:
            resp = requests.post(self._full_url, headers=self._headers(),
                                 json=payload, timeout=15)
            return self._result(resp)
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    # ---------- MULTIPART (rasm + video fayl bilan) ----------
    def _send_multipart(self, payload):
        image_paths = payload.get("image_paths") or []
        if not self.send_images:
            image_paths = []   # rasm yuborilmaydi (faqat video + matn)
        video_path = payload.get("video_path")

        # RASM kutish: raqam bor-u rasm hali yo'q — Dahua katta rasmni 30-60s
        # kechiktirib yuboradi; station late-image watcher rasm kelgach payload'ni
        # yangilaydi (update_outbox_payload). Shu oynada yubormay turamiz —
        # hodisa serverga RASM BILAN yetsin. Oyna tugasa rasmsiz ketadi.
        if (self.send_images and payload.get("plate") and not image_paths
                and _event_age_s(payload) < IMAGE_WAIT_MAX_S):
            return False, "rasm kutilyapti (keyin qayta urinamiz)"

        # video kutilyapti-yu hali diskda yo'q -> tayyor emas, keyin qayta urinamiz.
        # LEKIN abadiy emas: hodisa juda eskirgan bo'lsa (yozish crash bo'lgan,
        # fayl hech qachon paydo bo'lmaydi) — VIDEOSIZ yuboramiz, hodisa yo'qolmasin.
        if video_path and not os.path.exists(video_path):
            if _event_age_s(payload) < VIDEO_WAIT_MAX_S:
                return False, "video hali tayyor emas (keyin qayta urinamiz)"
            payload = dict(payload)
            payload["video_path"] = None
            video_path = None

        existing_images = [p for p in image_paths if os.path.exists(p)]
        has_video = bool(video_path and os.path.exists(video_path))

        # Hech qanday fayl yo'q (video yozilmadi, rasm yo'q/o'chirilgan) ->
        # multipart o'rniga JSON yuboramiz. Aks holda requests bo'sh files bilan
        # form-urlencoded yuboradi va server 400 "JSON xato" beradi.
        if not existing_images and not has_video:
            meta = {k: v for k, v in payload.items() if k != "image_paths"}
            meta["image_paths"] = []
            return self._send_json(meta)

        # metadata — fayl yo'llari olib tashlanadi (fayllar alohida part bo'lib ketadi)
        meta = {k: v for k, v in payload.items()
                if k not in ("image_paths", "video_path")}

        open_files = []
        files = []
        try:
            for p in existing_images:
                f = open(p, "rb")
                open_files.append(f)
                files.append(("images", (os.path.basename(p), f, "image/jpeg")))
            if has_video:
                f = open(video_path, "rb")
                open_files.append(f)
                files.append(("video", (os.path.basename(video_path), f, "video/mp4")))

            data = {"data": json.dumps(meta, ensure_ascii=False)}
            resp = requests.post(self._full_url, headers=self._headers(),
                                 data=data, files=files or None, timeout=120)
            return self._result(resp)
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
        finally:
            for f in open_files:
                try:
                    f.close()
                except Exception:
                    pass

    def _result(self, resp):
        if 200 <= resp.status_code < 300:
            return True, f"ok {resp.status_code}"
        # 409 = event_uid allaqachon bor -> dublikat, muvaffaqiyat deb qabul qilamiz
        if resp.status_code == 409:
            return True, "409 dublikat (allaqachon bor)"
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
