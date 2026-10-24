"""Mutable runtime settings, shared by reference across modules, so the tray
menu can adjust size/speed/behavior live without restarting the app.
"""
from dataclasses import dataclass

from .config import SPRITE_SCALE

SIZES = {"Small": 0.5, "Normal": SPRITE_SCALE, "Large": 1.2}
SPEEDS = {"Slow": 0.6, "Normal": 1.0, "Fast": 1.8}


@dataclass
class Settings:
    scale: float = SPRITE_SCALE
    speed_multiplier: float = 1.0
    climbing_enabled: bool = True
    sleep_enabled: bool = True
    effects_enabled: bool = True
    paused: bool = False


settings = Settings()
