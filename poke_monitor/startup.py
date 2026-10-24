"""Run-at-login toggle, via the per-user HKCU Run registry key (no admin needed)."""
import os
import sys
import winreg

from .config import APP_ID, ROOT_DIR

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = APP_ID


def _command() -> str:
    if getattr(sys, "frozen", False):  # packaged exe: it is the whole app
        return f'"{sys.executable}"'
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        pythonw = exe[: -len("python.exe")] + "pythonw.exe"
        if os.path.exists(pythonw):
            exe = pythonw  # no console window at login
    return f'"{exe}" "{os.path.join(ROOT_DIR, "run.py")}"'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _VALUE_NAME)
        return True
    except FileNotFoundError:
        return False


def set_enabled(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _command())
        else:
            try:
                winreg.DeleteValue(key, _VALUE_NAME)
            except FileNotFoundError:
                pass
