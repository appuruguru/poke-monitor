"""Windows desktop introspection: work area, virtual screen bounds, and the
list of "surfaces" (ground + visible window top edges) a pet can stand on.
"""
import ctypes
from collections import namedtuple
from ctypes import wintypes

import win32api
import win32con
import win32gui

Surface = namedtuple("Surface", "left right y hwnd")

_SM_XVIRTUALSCREEN = 76
_SM_YVIRTUALSCREEN = 77
_SM_CXVIRTUALSCREEN = 78
_SM_CYVIRTUALSCREEN = 79

_SPI_GETWORKAREA = 0x0030


def get_work_area():
    """Primary monitor's work area (left, top, right, bottom), excluding the taskbar."""
    rect = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(_SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
    return (rect.left, rect.top, rect.right, rect.bottom)


def get_virtual_screen():
    """Bounding box of all monitors combined: (left, top, right, bottom)."""
    x = win32api.GetSystemMetrics(_SM_XVIRTUALSCREEN)
    y = win32api.GetSystemMetrics(_SM_YVIRTUALSCREEN)
    w = win32api.GetSystemMetrics(_SM_CXVIRTUALSCREEN)
    h = win32api.GetSystemMetrics(_SM_CYVIRTUALSCREEN)
    return (x, y, x + w, y + h)


def _is_fullscreen(hwnd, rect):
    """True if the window's rect exactly covers its monitor (not just the work
    area), i.e. a fullscreen app/game/video rather than a normal maximized window.
    """
    try:
        monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        mon_left, mon_top, mon_right, mon_bottom = win32api.GetMonitorInfo(monitor)["Monitor"]
    except Exception:
        return False
    left, top, right, bottom = rect
    tol = 2
    return (
        abs(left - mon_left) <= tol
        and abs(top - mon_top) <= tol
        and abs(right - mon_right) <= tol
        and abs(bottom - mon_bottom) <= tol
    )


def _passes_basic_filters(hwnd, exclude_hwnds):
    if hwnd in exclude_hwnds:
        return False
    if not win32gui.IsWindowVisible(hwnd):
        return False
    if win32gui.IsIconic(hwnd):
        return False
    if not win32gui.GetWindowText(hwnd):
        return False
    ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    if ex_style & win32con.WS_EX_TOOLWINDOW:
        return False
    return True


def _covers_top_edge(occluder_rect, rect):
    """True if occluder_rect fully spans rect's width and its top edge lies
    within occluder_rect's vertical extent -- i.e. rect's whole top-edge
    strip (the part a pet would stand on) is hidden behind occluder_rect.
    """
    o_left, o_top, o_right, o_bottom = occluder_rect
    left, top, right, _bottom = rect
    return o_left <= left and o_right >= right and o_top <= top <= o_bottom


def get_surfaces(exclude_hwnds=frozenset()):
    """Ground (taskbar top) plus the top edge of every relevant *visible*
    window.

    EnumWindows walks windows top-to-bottom in Z-order, so for each window we
    check it against every higher (already-seen) window on the same monitor:
    if one of those fully covers this window's top-edge strip, this window is
    hidden behind it and isn't a landable surface -- whether or not that
    occluder itself happens to be "fullscreen". A fullscreen window is also
    never a landable surface itself (only the ground is, under one), but it
    still counts as an occluder for anything behind it.
    """
    work_left, work_top, work_right, work_bottom = get_work_area()
    surfaces = [Surface(work_left, work_right, work_bottom, None)]
    occluders_by_monitor = {}

    def _callback(hwnd, _extra):
        if not _passes_basic_filters(hwnd, exclude_hwnds):
            return True
        rect = win32gui.GetWindowRect(hwnd)
        left, top, right, bottom = rect
        if right - left < 80 or bottom - top < 40:
            return True

        try:
            # int(): MonitorFromWindow returns a new PyHANDLE each call, which
            # wouldn't match as a dict key.
            monitor = int(win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST))
        except Exception:
            monitor = None

        occluders = occluders_by_monitor.setdefault(monitor, [])

        occluded = any(_covers_top_edge(o, rect) for o in occluders)
        if not occluded and not _is_fullscreen(hwnd, rect):
            surfaces.append(Surface(left, right, top, hwnd))

        occluders.append(rect)  # every visible window can hide windows behind it
        return True

    win32gui.EnumWindows(_callback, None)
    return surfaces
