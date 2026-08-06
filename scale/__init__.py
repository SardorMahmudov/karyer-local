"""Tarozi paketi — drayverlar va vaznni barqarorlashtirish."""
from .base import ScaleReader, ScaleReading
from .stabilizer import WeightStabilizer
from .sim_driver import SimScaleReader
from .serial_driver import SerialScaleReader


def make_scale_reader(scale_cfg):
    """config.scale bo'yicha mos drayverni qaytaradi."""
    stype = scale_cfg.get("type", "serial")
    if stype == "sim":
        return SimScaleReader(scale_cfg)
    if stype == "tcp":
        # TCP drayver keyingi bosqichda; hozircha serial fallback
        from .serial_driver import SerialScaleReader as _S
        return _S(scale_cfg)
    return SerialScaleReader(scale_cfg)
