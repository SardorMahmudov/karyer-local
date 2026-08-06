#!/usr/bin/env python3
"""
Simulyator tarozi — apparatsiz test uchun.

Real KELI D12 kabi ishlaydi: bo'sh turadi (0), keyin "mashina keladi" —
vazn sakraydi va bir necha soniya silkinadi (mode algoritmini sinash uchun),
so'ng turg'unlashadi, biroz turadi va "mashina ketadi" (0 ga qaytadi).
"""

import time
import random
from .base import ScaleReader, ScaleReading


class SimScaleReader(ScaleReader):
    def _run(self):
        rng = random.Random(12345)   # takrorlanadigan test uchun
        while self._running:
            # --- bo'sh (mashina yo'q) ---
            for _ in range(15):
                if not self._running:
                    return
                self._emit(ScaleReading(0.0, raw="0"))
                time.sleep(0.1)

            # --- mashina keladi: haqiqiy vazn atrofida silkinish ---
            target = rng.choice([18500, 24200, 26750, 31200, 15800])
            # kirish payti — keskin tebranish (~2 s)
            for _ in range(20):
                if not self._running:
                    return
                noise = rng.randint(-400, 400)
                self._emit(ScaleReading(float(target + noise), raw=str(target + noise)))
                time.sleep(0.1)

            # --- turg'unlashadi: kichik tebranish, mode = target ---
            for _ in range(40):
                if not self._running:
                    return
                # ko'pincha aynan target, ba'zan ±10 (1 qadam), kamdan-kam katta spike
                noise = rng.choice([0, 0, 0, 0, 10, -10, 0, 10, 0, 200])  # 200 = chetdagi sakrash
                self._emit(ScaleReading(float(target + noise), raw=str(target + noise)))
                time.sleep(0.1)

            # --- mashina ketadi ---
            for _ in range(8):
                if not self._running:
                    return
                self._emit(ScaleReading(0.0, raw="0"))
                time.sleep(0.1)
