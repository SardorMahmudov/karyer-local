#!/usr/bin/env python3
"""
Ma'lumotlar bazasi — SQLite.

Ikki jadval:
  - weigh_events : har bir tortish/o'tish hodisasi (raqam, vazn, vaqt, video, rasmlar)
  - outbox       : serverga yuborish navbati (pending -> sent, xato bo'lsa retry)
"""

import os
import json
import sqlite3
import threading
import time

from config import app_dir

BASE_DIR = app_dir()
DB_PATH = os.path.join(BASE_DIR, "karyer_server.db")

# SQLite'ni ko'p oqimdan xavfsiz ishlatish uchun oddiy qulf
_lock = threading.Lock()


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with _lock, _connect() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS weigh_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quarry_id     TEXT,
                station       TEXT,
                mode          TEXT,
                plate         TEXT,
                direction     TEXT,               -- in (kirish) | out (chiqish) | NULL
                weight        REAL,
                unit          TEXT DEFAULT 'kg',
                event_time    TEXT,
                video_path    TEXT,
                image_paths   TEXT,
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # eski bazalar uchun ustun qo'shish
        try:
            c.execute("ALTER TABLE weigh_events ADD COLUMN direction TEXT")
        except sqlite3.OperationalError:
            pass
        # har (stansiya, raqam) uchun oxirgi harakat — kirish/chiqishni almashtirish uchun
        c.execute("""
            CREATE TABLE IF NOT EXISTS vehicle_state (
                station    TEXT NOT NULL,
                plate      TEXT NOT NULL,
                last_dir   TEXT NOT NULL,         -- in | out
                updated_at REAL NOT NULL,
                entry_weight REAL,                -- kirish (bo'sh) vazni — vazn-yo'nalish uchun
                PRIMARY KEY (station, plate)
            )
        """)
        # eski bazaga entry_weight ustunini qo'shamiz (migratsiya)
        try:
            cols = [r[1] for r in c.execute("PRAGMA table_info(vehicle_state)")]
            if "entry_weight" not in cols:
                c.execute("ALTER TABLE vehicle_state ADD COLUMN entry_weight REAL")
        except Exception:
            pass
        c.execute("""
            CREATE TABLE IF NOT EXISTS outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id      INTEGER,
                payload       TEXT NOT NULL,
                status        TEXT DEFAULT 'pending',   -- pending | sent | failed
                attempts      INTEGER DEFAULT 0,
                last_error    TEXT,
                next_retry_at REAL DEFAULT 0,
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES weigh_events (id)
            )
        """)
        conn.commit()


def insert_event(ev):
    """Hodisani weigh_events ga yozadi, id qaytaradi."""
    with _lock, _connect() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO weigh_events
              (quarry_id, station, mode, plate, direction, weight, unit, event_time, video_path, image_paths)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            ev.get("quarry_id"), ev.get("station"), ev.get("mode"),
            ev.get("plate"), ev.get("direction"),
            ev.get("weight"), ev.get("unit", "kg"),
            ev.get("event_time"), ev.get("video_path"),
            json.dumps(ev.get("image_paths", []), ensure_ascii=False),
        ))
        conn.commit()
        return c.lastrowid


def set_event_images(event_id, paths):
    """Hodisaning rasm yo'llarini KEYIN yangilaydi — Dahua katta rasmni
    30-60s kechiktirib yuborganda (late-image) lokal yozuv ham to'g'ri tursin."""
    with _lock, _connect() as conn:
        conn.execute("UPDATE weigh_events SET image_paths=? WHERE id=?",
                     (json.dumps(paths, ensure_ascii=False), event_id))
        conn.commit()


def toggle_direction(station, plate, reset_hours=12):
    """
    Mashina harakat yo'nalishini aniqlaydi (bitta darvozadan kirish/chiqish).

    Mantiq: har (stansiya, raqam) juftligi uchun oxirgi harakat saqlanadi.
      - birinchi ko'rinish            -> 'in'  (kirish)
      - oxirgisi 'in' bo'lsa          -> 'out' (chiqish)
      - oxirgisi 'out' bo'lsa         -> 'in'  (yana kirish)
      - oxirgi harakatdan reset_hours dan ko'p o'tgan bo'lsa -> 'in'
        (masalan tunda chiqib ketgan, ertalab yana kelgan)
    """
    now = time.time()
    with _lock, _connect() as conn:
        c = conn.cursor()
        c.execute("SELECT last_dir, updated_at FROM vehicle_state WHERE station=? AND plate=?",
                  (station, plate))
        row = c.fetchone()
        if row is None:
            direction = "in"
        else:
            last_dir, updated_at = row
            if reset_hours and (now - updated_at) > reset_hours * 3600:
                direction = "in"
            else:
                direction = "out" if last_dir == "in" else "in"
        c.execute("""
            INSERT INTO vehicle_state (station, plate, last_dir, updated_at)
            VALUES (?,?,?,?)
            ON CONFLICT(station, plate) DO UPDATE SET last_dir=excluded.last_dir,
                                                      updated_at=excluded.updated_at
        """, (station, plate, direction, now))
        conn.commit()
        return direction


def trip_direction(station, plate, weight, threshold_kg=5000, reset_hours=24):
    """VAZN bo'yicha kirish/chiqish (bir yo'lakli tarozi — video yo'nalish
    ishonchsiz). IKKI oqim bor, ikkalasida ham 2-tortish CHIQISH:
      - SOTUV:  bo'sh kiradi (14t) -> YUKLAB chiqadi (44t)   — vazn OSHADI
      - KARYER: yuklangan kiradi (40t) -> BO'SH chiqadi (14t) — vazn KAMAYADI
    Shuning uchun FARQNING ABSOLYUT qiymati ishlatiladi:
      - birinchi tortish (yoki oldingisi CHIQISH) -> 'in' (kirish)
      - oldingisi KIRISH va |joriy - kirish| >= threshold_kg -> 'out'
        (yuk ortildi YOKI tushirildi — reys tugadi)
      - |farq| < threshold_kg -> yana 'in' (qimirlash/yuklanmagan qayta o'tish)
      - reset_hours dan ko'p o'tsa -> 'in' (yangi kun/reys)
    Mashina sotuvmi-karyermi ekanini BACKEND aniqlaydi (tarozidan oldin
    karyerdan chiqqan bo'lsa karyer) — local faqat in/out beradi."""
    now = time.time()
    with _lock, _connect() as conn:
        c = conn.cursor()
        c.execute("SELECT last_dir, updated_at, entry_weight FROM vehicle_state "
                  "WHERE station=? AND plate=?", (station, plate))
        row = c.fetchone()
        direction = "in"
        entry_w = weight
        if row is not None:
            last_dir, updated_at, prev_entry = row
            stale = reset_hours and (now - updated_at) > reset_hours * 3600
            if (not stale and last_dir == "in" and prev_entry is not None
                    and weight is not None
                    and abs(weight - prev_entry) >= threshold_kg):
                direction = "out"           # yuk ortildi/tushirildi — reys tugadi
                entry_w = prev_entry        # bazani saqlaymiz (netto uchun)
            else:
                direction = "in"            # yangi/qayta kirish
                entry_w = weight
        c.execute("""
            INSERT INTO vehicle_state (station, plate, last_dir, updated_at, entry_weight)
            VALUES (?,?,?,?,?)
            ON CONFLICT(station, plate) DO UPDATE SET last_dir=excluded.last_dir,
                updated_at=excluded.updated_at, entry_weight=excluded.entry_weight
        """, (station, plate, direction, now, entry_w))
        conn.commit()
        return direction


def set_direction_state(station, plate, direction):
    """Video (chiziq kesish) aniqlagan yo'nalishni holatga yozadi —
    keyingi raqam-almashinuv fallback hisobi to'g'ri davom etishi uchun."""
    with _lock, _connect() as conn:
        conn.execute("""
            INSERT INTO vehicle_state (station, plate, last_dir, updated_at)
            VALUES (?,?,?,?)
            ON CONFLICT(station, plate) DO UPDATE SET last_dir=excluded.last_dir,
                                                      updated_at=excluded.updated_at
        """, (station, plate, direction, time.time()))
        conn.commit()


def enqueue_outbox(event_id, payload):
    """Serverga yuborish uchun navbatga qo'shadi."""
    with _lock, _connect() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO outbox (event_id, payload, status, next_retry_at) VALUES (?,?, 'pending', 0)",
            (event_id, json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()
        return c.lastrowid


def update_outbox_payload(event_id, payload):
    """Hodisaning navbatdagi payload'ini yangilaydi (masalan video yozilmasa
    video_path=None qilinadi — outbox yo'q faylni kutib qolmasin)."""
    with _lock, _connect() as conn:
        conn.execute(
            "UPDATE outbox SET payload=? WHERE event_id=? AND status='pending'",
            (json.dumps(payload, ensure_ascii=False), event_id),
        )
        conn.commit()


def fetch_unqueued_events(days=3, limit=200):
    """weigh_events'da bor-u outbox'ga TUSHMAGAN hodisalar (eski versiya
    restart paytida yo'qotganlari) — startup'da qayta navbatga qo'yish uchun."""
    with _lock, _connect() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT e.id, e.quarry_id, e.station, e.plate, e.direction, e.weight,
                   e.unit, e.event_time, e.video_path, e.image_paths
            FROM weigh_events e
            LEFT JOIN outbox o ON o.event_id = e.id
            WHERE o.id IS NULL
              AND e.created_at >= datetime('now', ?)
            ORDER BY e.id ASC LIMIT ?
        """, (f"-{int(days)} days", limit))
        return c.fetchall()


def fetch_pending(limit=20):
    """Yuborishga tayyor (vaqti kelgan) yozuvlar."""
    now = time.time()
    with _lock, _connect() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, event_id, payload, attempts FROM outbox
            WHERE status='pending' AND next_retry_at <= ?
            ORDER BY id ASC LIMIT ?
        """, (now, limit))
        return c.fetchall()


def mark_sent(outbox_id):
    with _lock, _connect() as conn:
        conn.execute("UPDATE outbox SET status='sent', last_error=NULL WHERE id=?", (outbox_id,))
        conn.commit()


def mark_retry(outbox_id, attempts, error, delay):
    """Xatodan keyin backoff bilan qayta urinishga rejalashtiradi."""
    next_at = time.time() + delay
    with _lock, _connect() as conn:
        conn.execute("""
            UPDATE outbox SET attempts=?, last_error=?, next_retry_at=? WHERE id=?
        """, (attempts, str(error)[:500], next_at, outbox_id))
        conn.commit()


def pending_count():
    with _lock, _connect() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM outbox WHERE status='pending'")
        return c.fetchone()[0]


def prune_sent(days=30):
    """Yuborilgan (sent) eski outbox yozuvlarini o'chiradi — baza shishmasin.
    weigh_events tegilmaydi (lokal tarix sifatida qoladi)."""
    with _lock, _connect() as conn:
        c = conn.cursor()
        c.execute("""
            DELETE FROM outbox
            WHERE status='sent'
              AND created_at < datetime('now', ?)
        """, (f"-{int(days)} days",))
        n = c.rowcount
        conn.commit()
        if n:
            print(f"[db] {n} ta eski yuborilgan yozuv tozalandi")
        return n
