#!/usr/bin/env python3
"""
Tarozi drayveri uchun umumiy interfeys.

Har bir drayver (serial / tcp / sim) uzluksiz vazn o'qib, har bir o'qishni
callback(reading) orqali yuboradi. reading = ScaleReading.
"""

import time
import threading


class ScaleReading:
    __slots__ = ("weight", "unit", "raw", "ts")

    def __init__(self, weight, unit="kg", raw="", ts=None):
        self.weight = weight          # float (kg) yoki None (o'qib bo'lmadi)
        self.unit = unit
        self.raw = raw                # xom satr/frame (debug uchun)
        self.ts = ts if ts is not None else time.time()

    def __repr__(self):
        return f"<ScaleReading {self.weight}{self.unit} @{self.ts:.2f}>"


class ScaleReader:
    """Bazaviy sinf — start(callback) / stop()."""

    def __init__(self, cfg):
        self.cfg = cfg
        self._callback = None
        self._thread = None
        self._running = False

    def start(self, callback):
        self._callback = callback
        self._running = True
        self._thread = threading.Thread(target=self._run, name="scale", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _emit(self, reading):
        if self._callback:
            self._callback(reading)

    def _run(self):
        raise NotImplementedError
