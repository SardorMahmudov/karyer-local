#!/usr/bin/env python3
"""
Vaznni barqarorlashtirish (TZ 4a).

Mashina taroziga chiqqanda silkinish tufayli raqamlar tez-tez o'zgaradi.
Bu sinf:
  1. Vazn `min_weight` chegarasidan oshib turg'un bo'lishini kutadi.
  2. `settle_time` davomida qiymatlar `stability_tolerance` ichida bo'lsa
     — barqaror deb hisoblaydi.
  3. Yakuniy vaznni barqaror oynadagi qiymatlarning MODE (eng ko'p
     takrorlangan) qiymati sifatida qaytaradi. Teng bo'lsa `tie_break`
     bo'yicha (default: eng katta — yukni kam ko'rsatmaslik uchun).
"""

from collections import Counter


class WeightStabilizer:
    def __init__(self, min_weight=500, settle_time=3.0, stability_tolerance=20,
                 division=10, tie_break="largest", min_samples=5):
        self.min_weight = float(min_weight)
        self.settle_time = float(settle_time)
        self.tolerance = float(stability_tolerance)
        self.division = max(1, int(division))
        self.tie_break = tie_break
        self.min_samples = int(min_samples)
        self.reset()

    # mashina "ketdi" deyish uchun ketma-ket shuncha past o'qish kerak
    # (silkinishda bir lahza pastga tushish qayta hodisa chiqarmasligi uchun)
    ABSENT_DEBOUNCE = 5

    def reset(self):
        """Yangi mashina uchun holatni tozalash."""
        self._samples = []          # [(ts, weight)] — mashina turgan vaqtdagi o'qishlar
        self._emitted = False       # shu mashina uchun natija berilganmi
        self._absent_count = 0      # ketma-ket past o'qishlar soni

    # ---- yordamchi ----
    def _round(self, w):
        """Tarozi qadamiga yaxlitlash."""
        d = self.division
        return int(round(w / d) * d)

    def _mode(self, weights):
        """Eng ko'p takrorlangan yaxlitlangan qiymat (tie_break bilan)."""
        rounded = [self._round(w) for w in weights]
        counts = Counter(rounded)
        top = max(counts.values())
        winners = [val for val, cnt in counts.items() if cnt == top]
        if len(winners) == 1:
            return winners[0]
        if self.tie_break == "smallest":
            return min(winners)
        if self.tie_break == "first":
            for w in rounded:
                if w in winners:
                    return w
        return max(winners)   # default: largest

    # ---- asosiy API ----
    def feed(self, weight, ts):
        """
        Har bir vazn o'qishini beradi. Qaytaradi:
          - float: mashina barqaror, yakuniy (mode) vazn tayyor (bir marta)
          - None : hali barqaror emas yoki mashina yo'q
        """
        if weight is None:
            return None   # buzuq o'qish — e'tiborsiz (holatni buzmaymiz)

        if weight < self.min_weight:
            # past o'qish — darhol emas, ketma-ket ABSENT_DEBOUNCE marta
            # takrorlansagina "mashina ketdi" deb hisoblaymiz
            self._absent_count += 1
            if self._absent_count >= self.ABSENT_DEBOUNCE and (self._samples or self._emitted):
                self.reset()
            return None

        self._absent_count = 0
        self._samples.append((ts, weight))
        # xotira/tezlik: faqat oynaga sig'adigan oxirgi o'qishlarni saqlaymiz
        cutoff = ts - self.settle_time * 2
        if self._samples and self._samples[0][0] < cutoff:
            self._samples = [(t, w) for (t, w) in self._samples if t >= cutoff]
        if self._emitted:
            return None

        # oxirgi settle_time soniyadagi o'qishlar
        window = [(t, w) for (t, w) in self._samples if ts - t <= self.settle_time]
        if len(window) < self.min_samples:
            return None

        # oyna haqiqatan settle_time ni qamrab olganmi?
        if ts - window[0][0] < self.settle_time * 0.8:
            return None

        ws = [w for _, w in window]
        if not self._spread_ok(ws):
            return None   # hali silkinyapti

        # barqaror — mode olamiz
        self._emitted = True
        return float(self._mode(ws))

    def _spread_ok(self, ws):
        """Tebranish tolerance ichidami? Chetdagi bir-ikki sakrash (spike)
        natijani bloklamasligi uchun eng katta/kichik ~10% ni tashlab yuboramiz."""
        s = sorted(ws)
        if len(s) >= 8:
            cut = max(1, len(s) // 10)
            s = s[cut:-cut]
        return (s[-1] - s[0]) <= self.tolerance

    @property
    def vehicle_present(self):
        return bool(self._samples)

    @property
    def emitted(self):
        return self._emitted
