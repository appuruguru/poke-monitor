"""PetManager, system tray icon, and the shared tick loop that drives every
active pet. This module owns the single Tk root and the pystray icon thread.
"""
import ctypes
import threading
import tkinter as tk
from ctypes import wintypes
from tkinter import messagebox

import pystray

from . import assets, startup, winutils
from .config import APP_ID, APP_NAME, PETS, TICK_MS
from .icon import make_icon
from .pet import Pet
from .settings import SIZES, SPEEDS, settings


class PetManager:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.pets: dict[str, Pet] = {}

    def spawn(self, name: str):
        if name in self.pets:
            return
        self.pets[name] = Pet(name, self.root, on_remove=self.despawn)

    def despawn(self, name: str):
        pet = self.pets.pop(name, None)
        if pet is not None:
            pet.destroy()

    def despawn_all(self):
        for name in list(self.pets):
            self.despawn(name)

    def rescale_all(self):
        for pet in self.pets.values():
            pet.rescale()

    def hwnds(self):
        return {pet.hwnd for pet in self.pets.values()}

    def tick(self):
        surfaces = winutils.get_surfaces(exclude_hwnds=self.hwnds())
        for pet in list(self.pets.values()):
            pet.tick(surfaces, TICK_MS)


def _build_tray_icon(manager: PetManager, root: tk.Tk) -> pystray.Icon:
    # Tk isn't thread-safe and pystray callbacks run on the tray thread, so
    # anything touching pets/windows is bounced onto the Tk thread via after().

    def toggle_pet(name):
        def handler(icon, item):
            def action():
                if name in manager.pets:
                    manager.despawn(name)
                else:
                    manager.spawn(name)
            root.after(0, action)
        return handler

    def toggle_pause(icon, item):
        settings.paused = not settings.paused

    def set_size(label):
        def handler(icon, item):
            def action():
                settings.scale = SIZES[label]
                manager.rescale_all()
            root.after(0, action)
        return handler

    def set_speed(label):
        def handler(icon, item):
            settings.speed_multiplier = SPEEDS[label]
        return handler

    def toggle_climbing(icon, item):
        settings.climbing_enabled = not settings.climbing_enabled

    def toggle_sleep(icon, item):
        settings.sleep_enabled = not settings.sleep_enabled

    def toggle_effects(icon, item):
        settings.effects_enabled = not settings.effects_enabled

    def toggle_startup(icon, item):
        startup.set_enabled(not startup.is_enabled())

    def quit_app(icon, item):
        icon.stop()
        root.after(0, root.quit)

    pet_items = [
        pystray.MenuItem(
            name.capitalize(), toggle_pet(name), checked=lambda item, n=name: n in manager.pets
        )
        for name in PETS
    ]
    size_menu = pystray.Menu(*[
        pystray.MenuItem(
            label, set_size(label), radio=True,
            checked=lambda item, v=value: settings.scale == v,
        )
        for label, value in SIZES.items()
    ])
    speed_menu = pystray.Menu(*[
        pystray.MenuItem(
            label, set_speed(label), radio=True,
            checked=lambda item, v=value: settings.speed_multiplier == v,
        )
        for label, value in SPEEDS.items()
    ])
    behavior_menu = pystray.Menu(
        pystray.MenuItem("Allow climbing", toggle_climbing, checked=lambda item: settings.climbing_enabled),
        pystray.MenuItem("Allow sleeping", toggle_sleep, checked=lambda item: settings.sleep_enabled),
        pystray.MenuItem("Special effects", toggle_effects, checked=lambda item: settings.effects_enabled),
        pystray.MenuItem("Speed", speed_menu),
    )

    items = [
        *pet_items,
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(lambda item: "Resume" if settings.paused else "Pause", toggle_pause),
        pystray.MenuItem("Size", size_menu),
        pystray.MenuItem("Behavior", behavior_menu),
        pystray.MenuItem("Run at startup", toggle_startup, checked=lambda item: startup.is_enabled()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", quit_app),
    ]
    return pystray.Icon(APP_ID, make_icon(), APP_NAME, pystray.Menu(*items))


_ERROR_ALREADY_EXISTS = 183
_single_instance_mutex = None  # kept alive for the life of the process


def _already_running() -> bool:
    """True if another copy holds the per-session mutex (so a second launch doesn't double the pets)."""
    global _single_instance_mutex
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    _single_instance_mutex = kernel32.CreateMutexW(None, False, f"Local\\{APP_ID}-single-instance")
    return ctypes.get_last_error() == _ERROR_ALREADY_EXISTS


def _ensure_sprites(root: tk.Tk) -> None:
    todo = assets.missing_sprites()
    if not todo:
        return
    splash = tk.Toplevel(root)
    splash.title(APP_NAME)
    splash.attributes("-topmost", True)
    splash.resizable(False, False)
    label = tk.Label(splash, text="Preparing…", padx=40, pady=24)
    label.pack()

    def progress(i, total, name):
        label.config(text=f"Downloading sprites ({i}/{total}): {name.capitalize()}…")
        splash.update()

    splash.update()
    try:
        assets.download_sprites(todo, progress)
    finally:
        splash.destroy()


def run():
    root = tk.Tk()
    root.withdraw()

    if _already_running():
        messagebox.showinfo(APP_NAME, f"{APP_NAME} is already running. Look for its pokeball icon in the system tray.")
        return

    try:
        _ensure_sprites(root)
    except OSError as exc:
        messagebox.showerror(
            APP_NAME,
            f"Couldn't download the sprites on first launch. Check your internet connection and try again.\n\n{exc}",
        )
        return

    manager = PetManager(root)
    for name in PETS:
        manager.spawn(name)

    icon = _build_tray_icon(manager, root)
    threading.Thread(target=icon.run, daemon=True).start()

    def loop():
        if not settings.paused:
            manager.tick()
        root.after(TICK_MS, loop)

    root.after(TICK_MS, loop)
    try:
        root.mainloop()
    finally:
        manager.despawn_all()


if __name__ == "__main__":
    run()
